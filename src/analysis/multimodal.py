import json
import logging
from typing import Any, Dict, cast

import google.generativeai as genai
import pandas as pd

from src.analysis.chart import ChartGenerator
from src.analysis.market_data import MarketDataFetcher
from src.config import Config
from src.data.social import RedditScraper
from src.utils.gemini_key_manager import get_key_manager

logger = logging.getLogger("MultimodalAnalyst")


def _normalize_ticker_candidates(ticker: str) -> tuple[str, list[str]]:
    cleaned_ticker = (ticker or "").strip().upper()
    if not cleaned_ticker:
        return "", []

    if cleaned_ticker.isdigit():
        return cleaned_ticker, [f"{cleaned_ticker}.KS", f"{cleaned_ticker}.KQ"]

    return cleaned_ticker, [cleaned_ticker]


def resolve_price_history(
    market_fetcher: MarketDataFetcher,
    ticker: str,
    period: str = "6mo",
) -> tuple[str, str | None, pd.DataFrame]:
    cleaned_ticker, candidates = _normalize_ticker_candidates(ticker)
    if not candidates:
        return cleaned_ticker, None, pd.DataFrame()

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            df = market_fetcher.fetch_history(candidate, period=period)
        except Exception as exc:
            last_error = exc
            continue

        if df is not None and not df.empty:
            return cleaned_ticker, candidate, df

    if last_error is not None:
        logger.warning(f"{cleaned_ticker} 데이터 조회 재시도 실패: {last_error}")

    return cleaned_ticker, None, pd.DataFrame()


def _classify_rsi(rsi_value: float) -> str:
    if rsi_value >= 70:
        return "과매수 구간"
    if rsi_value <= 30:
        return "과매도 구간"
    return "중립 구간"


def _get_numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        return pd.Series(dtype=float)
    return cast(pd.Series, pd.to_numeric(df[column], errors="coerce")).dropna()


def _build_market_context_summary(df: pd.DataFrame) -> str:
    close = _get_numeric_series(df, "Close")
    if len(close) < 20:
        return "시장 컨텍스트:\n- 데이터가 부족해 추세 맥락을 안정적으로 계산하지 못했습니다."

    latest_close = float(close.iloc[-1])
    ma20_series = cast(pd.Series, close.rolling(window=20, min_periods=20).mean())
    ma20 = float(ma20_series.dropna().iloc[-1])
    if latest_close > ma20:
        short_trend = "20일선 위의 단기 상승 흐름"
    elif latest_close < ma20:
        short_trend = "20일선 아래의 단기 약세 흐름"
    else:
        short_trend = "20일선 부근의 중립 흐름"

    if len(close) >= 60:
        ma60_series = cast(pd.Series, close.rolling(window=60, min_periods=60).mean())
        ma60 = float(ma60_series.dropna().iloc[-1])
        medium_trend = "60일선 위" if latest_close > ma60 else "60일선 아래"
    else:
        medium_trend = "60일선 데이터 부족"

    momentum_base = float(close.iloc[-20])
    momentum_pct = ((latest_close - momentum_base) / momentum_base * 100) if momentum_base else 0.0

    return (
        "시장 컨텍스트:\n"
        f"- 단기 추세: {short_trend}\n"
        f"- 중기 위치: {medium_trend}\n"
        f"- 20거래일 모멘텀: {momentum_pct:+.2f}%"
    )


def _build_technical_summary(df: pd.DataFrame) -> str:
    close = _get_numeric_series(df, "Close")
    if len(close) < 26:
        return "기술 지표 요약:\n- 데이터가 부족해 RSI/MACD/볼린저 밴드를 안정적으로 계산하지 못했습니다."

    latest_close = float(close.iloc[-1])
    daily_change = close.pct_change().dropna()
    daily_change_pct = float(daily_change.iloc[-1] * 100) if not daily_change.empty else 0.0

    delta = cast(pd.Series, close.diff())
    gain = cast(pd.Series, delta.clip(lower=0))
    loss = cast(pd.Series, -delta.clip(upper=0))
    avg_gain = cast(pd.Series, gain.rolling(window=14, min_periods=14).mean())
    avg_loss = cast(pd.Series, loss.rolling(window=14, min_periods=14).mean())
    safe_avg_loss = cast(pd.Series, avg_loss.replace(0, pd.NA))
    rs = cast(pd.Series, avg_gain / safe_avg_loss)
    rsi = cast(pd.Series, 100 - (100 / (1 + rs)))
    latest_rsi = rsi.dropna()
    rsi_text = "계산 불가"
    if not latest_rsi.empty:
        latest_rsi_value = float(latest_rsi.iloc[-1])
        rsi_text = f"{latest_rsi_value:.1f} ({_classify_rsi(latest_rsi_value)})"

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    latest_macd = float(macd_line.iloc[-1])
    latest_signal = float(signal_line.iloc[-1])
    latest_hist = float(macd_hist.iloc[-1])
    if latest_macd > latest_signal:
        macd_bias = "상방 우위"
    elif latest_macd < latest_signal:
        macd_bias = "하방 우위"
    else:
        macd_bias = "중립"

    middle_band = cast(pd.Series, close.rolling(window=20, min_periods=20).mean())
    band_std = cast(pd.Series, close.rolling(window=20, min_periods=20).std())
    upper_band = cast(pd.Series, middle_band + (band_std * 2))
    lower_band = cast(pd.Series, middle_band - (band_std * 2))
    bollinger_text = "계산 불가"
    latest_middle = middle_band.dropna()
    latest_upper = upper_band.dropna()
    latest_lower = lower_band.dropna()
    if not latest_middle.empty and not latest_upper.empty and not latest_lower.empty:
        mid_value = float(latest_middle.iloc[-1])
        upper_value = float(latest_upper.iloc[-1])
        lower_value = float(latest_lower.iloc[-1])
        band_range = upper_value - lower_value
        if band_range > 0:
            position = (latest_close - lower_value) / band_range
            if position >= 0.8:
                bollinger_state = "상단 근접"
            elif position <= 0.2:
                bollinger_state = "하단 근접"
            else:
                bollinger_state = "중앙권"
        else:
            bollinger_state = "밴드 폭 협소"
        bollinger_text = f"중심선 {mid_value:.2f}, 상태 {bollinger_state}"

    volume = _get_numeric_series(df, "Volume")
    volume_text = "거래량 데이터 없음"
    if len(volume) >= 20:
        current_volume = float(volume.iloc[-1])
        avg_volume = float(volume.tail(20).mean())
        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
            volume_text = f"최근 거래량은 20일 평균 대비 {volume_ratio:.2f}배"

    return (
        "기술 지표 요약:\n"
        f"- 종가: {latest_close:.2f} (전일 대비 {daily_change_pct:+.2f}%)\n"
        f"- RSI(14): {rsi_text}\n"
        f"- MACD: {latest_macd:.2f}, 시그널: {latest_signal:.2f}, 히스토그램: {latest_hist:.2f} ({macd_bias})\n"
        f"- 볼린저 밴드(20, 2): {bollinger_text}\n"
        f"- 거래량: {volume_text}"
    )


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class MultimodalAnalyst:
    """뮤티모달 통합 분석기."""

    def __init__(self):
        self.market_fetcher = MarketDataFetcher()
        self.social_scraper = RedditScraper()
        self.chart_generator = ChartGenerator()

        self.model = None
        key_manager = get_key_manager()
        first_key = key_manager.get_available_key()
        if first_key:
            try:
                genai.configure(api_key=first_key)
                self.model = genai.GenerativeModel(Config.LLM_MODEL_NAME)
            except Exception as e:
                logger.error(f"Gemini 초기화 실패: {e}")

    def analyze_stock(self, ticker: str) -> Dict[str, Any]:
        result = {
            "signal": "NEUTRAL",
            "confidence": 0.0,
            "reason": "분석에 필요한 데이터가 부족하거나 분석에 실패했습니다.",
            "technical_summary": "",
            "market_context_summary": "",
            "analysis_sources": [],
            "key_drivers": [],
            "risk_factors": [],
        }

        if not self.model:
            return result

        cleaned_ticker, selected_ticker, df = resolve_price_history(self.market_fetcher, ticker, period="6mo")
        if not cleaned_ticker:
            result["reason"] = "종목 코드를 입력하세요."
            return result

        try:
            if df.empty or selected_ticker is None:
                logger.warning(f"{cleaned_ticker} 데이터 없음")
                result["reason"] = f"{cleaned_ticker} 종목의 시장 데이터를 찾을 수 없습니다."
                return result

            chart_bytes = self.chart_generator.generate_chart(df, title=f"{cleaned_ticker} 분석")

            social_posts = self.social_scraper.fetch_hot_posts("stocks", limit=5)
            line_break = chr(10)
            social_text = "최근 소셜 반응 (r/stocks):" + line_break
            if social_posts:
                for post in social_posts:
                    social_text += f"- {post['title']} (감성 점수: {post['sentiment']:.2f})" + line_break
            else:
                social_text += "- 관련 소셜 데이터가 충분하지 않습니다." + line_break

            technical_summary = _build_technical_summary(df)
            market_context_summary = _build_market_context_summary(df)
            analysis_sources = ["시장 컨텍스트", "기술 지표", "소셜 심리"]
            result["technical_summary"] = technical_summary
            result["market_context_summary"] = market_context_summary
            result["analysis_sources"] = analysis_sources

            prompt_text = f"""
다음 종목 '{cleaned_ticker}'을 제공된 차트 이미지와 소셜 심리 요약을 바탕으로 분석하세요.

컨텍스트:
- 조회 심볼: {selected_ticker}
{social_text}
{market_context_summary}
{technical_summary}

작업:
1. 차트의 기술적 패턴(추세, 지지/저항, 거래량)을 분석하세요.
2. RSI, MACD, 볼린저 밴드, 거래량 등 제공된 기술 지표 요약을 함께 해석하세요.
3. 시장 컨텍스트를 바탕으로 핵심 판단 근거와 리스크 요인을 구조적으로 정리하세요.
4. 소셜 심리 맥락을 함께 고려하세요.
5. 최종 매매 신호를 매수, 매도, 보유 중 하나로 제시하세요.

출력 형식(JSON만):
{{
    "signal": "매수" or "매도" or "보유",
    "confidence": 0.0 to 1.0,
    "reason": "분석 근거를 한국어로 간결하게 설명",
    "key_drivers": ["핵심 판단 근거 1", "핵심 판단 근거 2"],
    "risk_factors": ["주의할 리스크 1", "주의할 리스크 2"]
}}
"""

            inputs: list[Any] = [prompt_text]
            if chart_bytes:
                inputs.append({"mime_type": "image/png", "data": chart_bytes})

            response = self.model.generate_content(inputs)
            text = response.text.replace("```json", "").replace("```", "").strip()

            try:
                parsed = json.loads(text)
                parsed["technical_summary"] = technical_summary
                parsed["market_context_summary"] = market_context_summary
                parsed["analysis_sources"] = analysis_sources
                parsed["key_drivers"] = _coerce_string_list(parsed.get("key_drivers"))
                parsed["risk_factors"] = _coerce_string_list(parsed.get("risk_factors"))
                return parsed
            except json.JSONDecodeError:
                logger.error(f"LLM 응답 파싱 실패: {text}")
                result["reason"] = "LLM 응답 형식을 해석하지 못했습니다."
                result["raw_text"] = text
        except Exception as e:
            logger.error(f"멀티모달 분석 중 오류: {e}")
            result["reason"] = str(e)

        return result
