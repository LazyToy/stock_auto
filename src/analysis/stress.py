import pandas as pd
import numpy as np
import os
from typing import Dict, List, Any, Optional
import logging
from src.analysis.market_data import MarketDataFetcher

logger = logging.getLogger("StressTester")

class Scenario:
    def __init__(
        self,
        name: str,
        start_date: str,
        end_date: str,
        description: str,
        scenario_type: str = "historical",
        shock_return: Optional[float] = None,
        asset_shocks: Optional[Dict[str, float]] = None,
    ):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.description = description
        self.scenario_type = scenario_type
        self.shock_return = shock_return
        self.asset_shocks = asset_shocks or {}

class StressTester:
    """
    포트폴리오 스트레스 테스트 시뮬레이터
    """
    SCENARIOS = {
        "2008_Financial_Crisis": Scenario("2008 Financial Crisis", "2008-09-01", "2008-11-30", "Lehman Brothers Bankruptcy"),
        "2020_Covid_Crash": Scenario("2020 Covid Crash", "2020-02-19", "2020-03-23", "Pandemic onset"),
        "2022_Inflation_Shock": Scenario("2022 Inflation Shock", "2022-01-01", "2022-10-14", "Aggressive Rate Hikes"),
        "2025_Liberation_Day_Tariff_Shock": Scenario(
            "2025 Liberation Day Tariff Shock",
            "2025-04-03",
            "2025-04-08",
            "Actual price path after broad U.S. reciprocal tariff announcement and trade-war selloff",
            scenario_type="historical",
            asset_shocks={
                "SPY": -0.12,
                "QQQ": -0.14,
                "IWM": -0.16,
                "DIA": -0.10,
                "XLI": -0.13,
                "XLY": -0.14,
                "SMH": -0.15,
                "SOXX": -0.15,
                "TLT": 0.04,
                "GLD": 0.03,
            },
        ),
        "2026_US_Iran_War_Hormuz_Shock": Scenario(
            "2026 U.S.-Iran War / Hormuz Shock",
            "2026-02-28",
            "2026-05-22",
            "Actual price path after Middle East military action and the de facto Strait of Hormuz closure",
            scenario_type="historical",
            asset_shocks={
                "XLE": 0.12,
                "XOM": 0.10,
                "CVX": 0.08,
                "OXY": 0.08,
                "USO": 0.25,
                "GLD": 0.08,
                "IAU": 0.08,
                "TLT": 0.04,
            },
        ),
        "2026_May_Long_Rate_Shock": Scenario(
            "2026 May Long-Rate Shock",
            "2026-05-15",
            "2026-05-22",
            "Actual price path during the May 2026 global bond rout and long-rate spike",
            scenario_type="historical",
            asset_shocks={
                "TLT": -0.08,
                "EDV": -0.10,
                "IEF": -0.04,
                "QQQ": -0.06,
                "SPY": -0.04,
                "IWM": -0.06,
                "SMH": -0.08,
                "SOXX": -0.08,
                "XLU": -0.04,
                "GLD": 0.03,
            },
        ),
    }
    SCENARIO_PROXY_RETURNS = {
        "2008_Financial_Crisis": -0.30,
        "2020_Covid_Crash": -0.34,
        "2022_Inflation_Shock": -0.25,
        "2025_Liberation_Day_Tariff_Shock": -0.12,
        "2026_US_Iran_War_Hormuz_Shock": -0.18,
        "2026_May_Long_Rate_Shock": -0.05,
    }
    HYPOTHETICAL_SCENARIOS = {
    }
    PRICE_BASIS = "Adjusted OHLC (yfinance auto_adjust=True)"
    USDKRW_TICKER = "KRW=X"
    MACRO_INDICATORS = [
        {"name": "USD/KRW", "symbol": "KRW=X", "unit": "KRW per USD"},
        {"name": "VIX", "symbol": "^VIX", "unit": "index"},
        {"name": "WTI Oil", "symbol": "CL=F", "unit": "USD/bbl"},
        {"name": "US 10Y Yield", "symbol": "^TNX", "unit": "yield"},
    ]
    BENCHMARKS = [
        {"symbol": "SPY", "name": "S&P 500"},
        {"symbol": "QQQ", "name": "Nasdaq 100"},
        {"symbol": "IWM", "name": "Russell 2000"},
        {"symbol": "TLT", "name": "Long Treasury"},
        {"symbol": "GLD", "name": "Gold"},
        {"symbol": "EWY", "name": "Korea ETF"},
    ]
    SECTOR_PROXY_ETFS = {
        "Technology": "XLK",
        "Communication Services": "XLC",
        "Consumer Cyclical": "XLY",
        "Consumer Defensive": "XLP",
        "Financial Services": "XLF",
        "Healthcare": "XLV",
        "Energy": "XLE",
        "Industrials": "XLI",
        "Utilities": "XLU",
        "Real Estate": "XLRE",
        "Basic Materials": "XLB",
    }
    KR_SECTOR_PROXY_ETFS = {
        "반도체": "SMH",
        "IT": "XLK",
        "바이오": "XLV",
        "헬스케어": "XLV",
        "금융": "XLF",
        "에너지": "XLE",
        "화학": "XLB",
        "자동차": "CARZ",
        "2차전지": "LIT",
    }
    DEFAULT_US_PROXY_ETF = "SPY"
    DEFAULT_KR_PROXY_ETF = "EWY"

    def __init__(self):
        self.market_fetcher = MarketDataFetcher()
        self._configure_yfinance_cache()

    def _configure_yfinance_cache(self):
        """yfinance 캐시 경로를 작업 디렉터리 안으로 고정한다."""
        try:
            import yfinance as yf

            cache_dir = os.path.join(os.getcwd(), ".yf-cache")
            os.makedirs(cache_dir, exist_ok=True)
            if hasattr(yf, "set_tz_cache_location"):
                yf.set_tz_cache_location(cache_dir)
        except Exception as exc:
            logger.warning(f"yfinance 캐시 경로 설정 실패: {exc}")

    def _extract_close_series(self, data: pd.DataFrame, ticker: str) -> pd.Series:
        """다운로드 결과에서 종가 시리즈를 안전하게 추출한다."""
        return self._extract_price_series(data, ticker, "Close")

    def _extract_price_series(self, data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
        """다운로드 결과에서 특정 가격 필드 시리즈를 안전하게 추출한다."""
        if isinstance(data.columns, pd.MultiIndex):
            for level in range(data.columns.nlevels):
                level_values = data.columns.get_level_values(level)
                if field not in level_values:
                    continue

                field_data = data.xs(field, axis=1, level=level)
                if isinstance(field_data, pd.Series):
                    return field_data.dropna()

                if ticker in field_data.columns:
                    selected = field_data[ticker]
                    if isinstance(selected, pd.DataFrame):
                        selected = selected.iloc[:, 0]
                    return selected.dropna()

                if field_data.shape[1] == 1:
                    return field_data.iloc[:, 0].dropna()

            raise KeyError(f"{field} series not found for {ticker}")
        return data[field].dropna()

    def _normalize_price_index(self, series: pd.Series) -> pd.Series:
        """가격 시리즈 인덱스를 timezone 없는 DatetimeIndex로 정규화한다."""
        normalized = series.copy()
        index = pd.DatetimeIndex(pd.to_datetime(normalized.index))
        if index.tz is not None:
            index = index.tz_convert(None)
        normalized.index = index
        return normalized.sort_index()

    def _download_start_for_entry(self, scenario: Scenario) -> str:
        """시작 전 거래일 종가 확보를 위해 다운로드 시작일을 앞당긴다."""
        return (pd.Timestamp(scenario.start_date) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

    def _download_end_inclusive(self, scenario: Scenario) -> str:
        """yfinance end 파라미터가 exclusive라 종료일 다음 날을 반환한다."""
        return (pd.Timestamp(scenario.end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    def _download_history(
        self,
        ticker: str,
        scenario: Optional[Scenario] = None,
        *,
        period: Optional[str] = None,
        auto_adjust: bool = True,
    ) -> pd.DataFrame:
        """yfinance 다운로드 호출을 한 곳으로 모아 테스트와 조정주가 기준을 단순화한다."""
        import yfinance as yf

        kwargs = {
            "progress": False,
            "auto_adjust": auto_adjust,
            "threads": False,
        }
        if period:
            kwargs["period"] = period
        elif scenario:
            kwargs["start"] = self._download_start_for_entry(scenario)
            kwargs["end"] = self._download_end_inclusive(scenario)

        return yf.download(ticker, **kwargs)

    def _is_krw_ticker(self, ticker: str) -> bool:
        """한국 상장 종목은 이미 원화 quote로 본다."""
        cleaned = str(ticker or "").strip().upper()
        return cleaned.isdigit() or cleaned.endswith((".KS", ".KQ"))

    def _quote_currency(self, ticker: str) -> str:
        return "KRW" if self._is_krw_ticker(ticker) else "USD"

    def _get_usdkrw_series(self, scenario: Scenario) -> Optional[pd.Series]:
        """시나리오 기간의 USD/KRW 환율 경로를 가져온다."""
        try:
            data = self._download_history(self.USDKRW_TICKER, scenario, auto_adjust=False)
            if data.empty:
                return None
            return self._normalize_price_index(
                self._extract_close_series(data, self.USDKRW_TICKER).astype(float)
            )
        except Exception as exc:
            logger.warning(f"USD/KRW 환율 다운로드 실패: {exc}")
            return None

    def _align_series_to_index(self, series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
        """일별 시계열을 다른 가격 인덱스에 맞춰 보간 없이 직전값으로 정렬한다."""
        return series.reindex(index).ffill().bfill()

    def _convert_series_to_krw(
        self,
        series: pd.Series,
        ticker: str,
        fx_series: Optional[pd.Series],
    ) -> pd.Series:
        """해외 종목 가격 시리즈를 USD/KRW로 원화 환산한다."""
        if self._is_krw_ticker(ticker) or fx_series is None or fx_series.empty:
            return series
        aligned_fx = self._align_series_to_index(fx_series, pd.DatetimeIndex(series.index))
        return series * aligned_fx

    def _first_trading_date(self, ticker: str) -> Optional[pd.Timestamp]:
        """종목의 최초 거래일을 조회한다. 실패하면 None을 반환한다."""
        try:
            data = self._download_history(ticker, period="max", auto_adjust=True)
            if data.empty:
                return None
            close = self._normalize_price_index(self._extract_close_series(data, ticker).astype(float))
            if close.empty:
                return None
            return pd.Timestamp(close.index[0])
        except Exception as exc:
            logger.warning(f"{ticker} 최초 거래일 조회 실패: {exc}")
            return None

    def _is_pre_listing_asset(self, ticker: str, scenario: Scenario) -> bool:
        """시나리오 종료 이후에야 상장된 종목인지 확인한다."""
        first_date = self._first_trading_date(ticker)
        if first_date is None:
            return False
        return first_date > pd.Timestamp(scenario.end_date)

    def _get_symbol_sector(self, ticker: str) -> str:
        """US는 yfinance sector, KR은 Naver WICS 캐시를 우선 사용해 섹터를 추정한다."""
        try:
            if self._is_krw_ticker(ticker):
                from src.crawling.sector_map_kr import SectorMapKR

                code = str(ticker).upper().replace(".KS", "").replace(".KQ", "")
                sector_map = SectorMapKR("sector_map_kr.json")
                sector_map.load(known_tickers=[code])
                return str(sector_map.lookup(code) or "")

            import yfinance as yf

            info = getattr(yf.Ticker(ticker), "info", {}) or {}
            return str(info.get("sector") or "")
        except Exception as exc:
            logger.warning(f"{ticker} 섹터 조회 실패: {exc}")
            return ""

    def _resolve_proxy_etf(self, ticker: str) -> Dict[str, str]:
        """종목 섹터에 대응하는 대표 ETF를 고른다."""
        sector = self._get_symbol_sector(ticker)
        if self._is_krw_ticker(ticker):
            for keyword, etf in self.KR_SECTOR_PROXY_ETFS.items():
                if keyword in sector:
                    return {"proxy_symbol": etf, "sector": sector or "Unknown"}
            return {"proxy_symbol": self.DEFAULT_KR_PROXY_ETF, "sector": sector or "Unknown"}

        proxy_symbol = self.SECTOR_PROXY_ETFS.get(sector, self.DEFAULT_US_PROXY_ETF)
        return {"proxy_symbol": proxy_symbol, "sector": sector or "Unknown"}

    def _build_asset_path_and_extreme(
        self,
        ticker: str,
        data: pd.DataFrame,
        scenario: Scenario,
        fx_series: Optional[pd.Series] = None,
        proxy_symbol: Optional[str] = None,
        sector: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """시작 전 종가 진입 기준의 가격 경로와 시나리오 고가/저가를 만든다."""
        start_date = pd.Timestamp(scenario.start_date)
        end_date = pd.Timestamp(scenario.end_date)

        source_ticker = proxy_symbol or ticker
        close = self._normalize_price_index(self._extract_close_series(data, source_ticker).astype(float))
        try:
            high = self._normalize_price_index(self._extract_price_series(data, source_ticker, "High").astype(float))
        except (KeyError, TypeError, ValueError):
            high = close
        try:
            low = self._normalize_price_index(self._extract_price_series(data, source_ticker, "Low").astype(float))
        except (KeyError, TypeError, ValueError):
            low = close

        close_krw = self._convert_series_to_krw(close, source_ticker, fx_series)
        high_krw = self._convert_series_to_krw(high, source_ticker, fx_series)
        low_krw = self._convert_series_to_krw(low, source_ticker, fx_series)
        fx_used = (not self._is_krw_ticker(source_ticker)) and fx_series is not None and not fx_series.empty

        scenario_close = close[(close.index >= start_date) & (close.index <= end_date)]
        scenario_close_krw = close_krw[(close_krw.index >= start_date) & (close_krw.index <= end_date)]
        if scenario_close.empty:
            return None

        entry_candidates = close[close.index < start_date]
        entry_candidates_krw = close_krw[close_krw.index < start_date]
        if entry_candidates.empty:
            entry_date = scenario_close.index[0]
            entry_close = float(scenario_close.iloc[0])
            entry_close_krw = float(scenario_close_krw.iloc[0])
            path_close = scenario_close_krw
            path_quote = scenario_close
            entry_note = "시작 전 거래일 종가가 없어 시나리오 첫 종가를 진입가로 사용"
        else:
            entry_date = entry_candidates.index[-1]
            entry_close = float(entry_candidates.iloc[-1])
            entry_close_krw = float(entry_candidates_krw.loc[entry_date])
            entry_point = pd.Series([entry_close_krw], index=pd.DatetimeIndex([entry_date]))
            quote_entry_point = pd.Series([entry_close], index=pd.DatetimeIndex([entry_date]))
            path_close = pd.concat([entry_point, scenario_close_krw])
            path_quote = pd.concat([quote_entry_point, scenario_close])
            entry_note = ""

        if len(path_close) < 2 or entry_close_krw == 0:
            return None

        scenario_high = high[(high.index >= start_date) & (high.index <= end_date)]
        scenario_low = low[(low.index >= start_date) & (low.index <= end_date)]
        scenario_high_krw = high_krw[(high_krw.index >= start_date) & (high_krw.index <= end_date)]
        scenario_low_krw = low_krw[(low_krw.index >= start_date) & (low_krw.index <= end_date)]
        if scenario_high.empty:
            scenario_high = scenario_close
            scenario_high_krw = scenario_close_krw
        if scenario_low.empty:
            scenario_low = scenario_close
            scenario_low_krw = scenario_close_krw

        high_value = float(scenario_high.max())
        low_value = float(scenario_low.min())
        exit_close = float(scenario_close.iloc[-1])
        high_value_krw = float(scenario_high_krw.max())
        low_value_krw = float(scenario_low_krw.min())
        exit_close_krw = float(scenario_close_krw.iloc[-1])

        return {
            "path_close": path_close,
            "path_quote": path_quote,
            "return": (exit_close_krw - entry_close_krw) / entry_close_krw,
            "quote_currency": self._quote_currency(source_ticker),
            "fx_used": fx_used,
            "proxy_symbol": proxy_symbol,
            "sector": sector,
            "extreme": {
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "scenario_start_date": start_date.strftime("%Y-%m-%d"),
                "scenario_end_date": end_date.strftime("%Y-%m-%d"),
                "entry_close": entry_close,
                "exit_close": exit_close,
                "scenario_high": high_value,
                "scenario_low": low_value,
                "entry_close_krw": entry_close_krw,
                "exit_close_krw": exit_close_krw,
                "scenario_high_krw": high_value_krw,
                "scenario_low_krw": low_value_krw,
                "scenario_high_return": (high_value_krw - entry_close_krw) / entry_close_krw,
                "scenario_low_return": (low_value_krw - entry_close_krw) / entry_close_krw,
                "quote_currency": self._quote_currency(source_ticker),
                "fx_used": fx_used,
                "proxy_symbol": proxy_symbol,
                "sector": sector,
                "entry_note": entry_note,
            },
        }

    def _get_proxy_return(self, scenario_name: str, ticker: Optional[str] = None) -> float:
        """다운로드 실패 시 사용할 시나리오 프록시 수익률을 반환한다."""
        scenario = self.available_scenarios().get(scenario_name)
        if scenario and ticker:
            asset_shock = scenario.asset_shocks.get(ticker.upper())
            if asset_shock is not None:
                return float(asset_shock)
        if scenario and scenario.shock_return is not None:
            return float(scenario.shock_return)
        return self.SCENARIO_PROXY_RETURNS.get(scenario_name, -0.20)

    @classmethod
    def available_scenarios(cls) -> Dict[str, Scenario]:
        """UI에서 사용할 수 있는 실제 기간 기반 시나리오 목록을 반환한다."""
        return cls.SCENARIOS.copy()

    def calculate_risk_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """
        수익률 시리즈를 기반으로 리스크 지표 계산
        """
        if returns.empty:
            return {}

        metrics = {}
        
        # Empirical VaR (Historical Simulation method)
        metrics['VaR_95'] = np.percentile(returns, 5)
        metrics['VaR_99'] = np.percentile(returns, 1)
        
        # CVaR (Expected Shortfall) - Average of losses exceeding VaR 95
        cvar_mask = returns <= metrics['VaR_95']
        metrics['CVaR_95'] = returns[cvar_mask].mean() if cvar_mask.any() else 0.0
        
        # Max Drawdown
        cum_returns = (1 + returns).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        metrics['Max_Drawdown'] = drawdown.min()
        
        return metrics

    def classify_stress_risk(
        self,
        portfolio_return: float,
        risk_metrics: Optional[Dict[str, float]] = None,
        data_quality: Optional[Dict[str, Any]] = None,
    ) -> str:
        """기간 손익, 경로 손실, 데이터 품질을 함께 반영한 위험 등급."""
        risk_values = [portfolio_return]
        if risk_metrics:
            for key in ("Max_Drawdown", "CVaR_95", "VaR_95"):
                value = risk_metrics.get(key)
                if value is not None and not pd.isna(value):
                    risk_values.append(float(value))

        worst_loss = min(risk_values) if risk_values else portfolio_return
        if worst_loss <= -0.20:
            base_level = "HIGH"
        elif worst_loss <= -0.10:
            base_level = "MEDIUM"
        else:
            base_level = "LOW"

        if data_quality and data_quality.get("level") == "LOW":
            if base_level == "HIGH":
                return "HIGH_DATA_LIMITED"
            if base_level == "MEDIUM":
                return "MEDIUM_DATA_LIMITED"
            return "DATA_LIMITED"

        if base_level == "HIGH":
            return "HIGH"
        if worst_loss <= -0.10:
            return "MEDIUM"
        return "LOW"

    def _build_data_quality(
        self,
        portfolio: Dict[str, float],
        real_data_tickers: List[str],
        proxy_tickers: List[str],
        notes: List[str],
        excluded_tickers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """실데이터/프록시 사용 비중을 요약한다."""
        excluded_tickers = excluded_tickers or []
        asset_count = len(portfolio)
        total_abs_weight = sum(abs(weight) for weight in portfolio.values()) or 1.0
        proxy_weight = sum(abs(portfolio.get(ticker, 0.0)) for ticker in proxy_tickers) / total_abs_weight
        excluded_weight = sum(abs(portfolio.get(ticker, 0.0)) for ticker in excluded_tickers) / total_abs_weight
        coverage = len(real_data_tickers) / asset_count if asset_count else 0.0

        if proxy_weight == 0:
            level = "HIGH"
        elif proxy_weight <= 0.30:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "asset_count": asset_count,
            "real_data_count": len(real_data_tickers),
            "proxy_count": len(proxy_tickers),
            "excluded_count": len(excluded_tickers),
            "coverage": coverage,
            "proxy_weight": proxy_weight,
            "excluded_weight": excluded_weight,
            "level": level,
            "notes": notes,
        }

    def _scenario_index(self, scenario: Scenario) -> pd.DatetimeIndex:
        """실데이터가 전부 없을 때 사용할 시나리오 기간 인덱스."""
        if scenario.start_date and scenario.end_date:
            return pd.DatetimeIndex(pd.to_datetime([scenario.start_date, scenario.end_date]))
        return pd.DatetimeIndex(pd.to_datetime(["2000-01-01", "2000-01-02"]))

    def _build_proxy_curve(self, index: pd.DatetimeIndex, proxy_return: float) -> pd.Series:
        """프록시 수익률만 있는 자산을 시나리오 기간 선형 경로로 표현한다."""
        if len(index) == 0:
            index = pd.DatetimeIndex(pd.to_datetime(["2000-01-01", "2000-01-02"]))
        if len(index) == 1:
            values = np.array([1.0 + proxy_return])
        else:
            values = np.linspace(1.0, 1.0 + proxy_return, len(index))
        return pd.Series(values, index=index)

    def _serialize_asset_price_paths(
        self,
        close_series_by_ticker: Dict[str, pd.Series],
        quote_series_by_ticker: Optional[Dict[str, pd.Series]] = None,
        asset_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Chart-ready per-asset close paths for scenario-period visualization."""
        rows: List[Dict[str, Any]] = []
        quote_series_by_ticker = quote_series_by_ticker or {}
        asset_metadata = asset_metadata or {}
        for ticker, close in close_series_by_ticker.items():
            if close is None or close.empty:
                continue

            close = self._normalize_price_index(close.astype(float))
            quote_close = quote_series_by_ticker.get(ticker, close)
            quote_close = self._normalize_price_index(quote_close.astype(float))
            entry_close = float(close.iloc[0])
            if entry_close == 0:
                continue
            quote_currency = asset_metadata.get(ticker, {}).get("quote_currency", self._quote_currency(ticker))
            proxy_symbol = asset_metadata.get(ticker, {}).get("proxy_symbol")

            for index, value in close.items():
                quote_value = quote_close.reindex(pd.DatetimeIndex([index])).ffill().bfill()
                display_close = float(quote_value.iloc[0]) if not quote_value.empty else float(value)
                rows.append(
                    {
                        "symbol": ticker,
                        "date": index.strftime("%Y-%m-%d") if hasattr(index, "strftime") else str(index),
                        "close": display_close,
                        "close_krw": float(value),
                        "return": float((value - entry_close) / entry_close),
                        "indexed_price": float(value / entry_close * 100.0),
                        "quote_currency": quote_currency,
                        "proxy_symbol": proxy_symbol,
                    }
                )
        return rows

    def _build_path_result(
        self,
        portfolio: Dict[str, float],
        total_value: float,
        close_series_by_ticker: Dict[str, pd.Series],
        asset_returns: Dict[str, float],
        fallback_index: Optional[pd.DatetimeIndex] = None,
    ) -> Dict[str, Any]:
        """종목별 가격 경로로 포트폴리오 equity curve와 경로 리스크를 만든다."""
        indexes = [series.index for series in close_series_by_ticker.values() if not series.empty]
        if indexes:
            combined_index = indexes[0]
            for index in indexes[1:]:
                combined_index = combined_index.union(index)
            combined_index = pd.DatetimeIndex(combined_index).sort_values()
        else:
            combined_index = (
                fallback_index
                if fallback_index is not None and len(fallback_index) > 0
                else pd.DatetimeIndex(pd.to_datetime(["2000-01-01", "2000-01-02"]))
            )

        portfolio_curve = pd.Series(1.0, index=combined_index, dtype=float)
        contribution_curve = pd.Series(0.0, index=combined_index, dtype=float)

        for ticker, weight in portfolio.items():
            close = close_series_by_ticker.get(ticker)
            if close is not None and not close.empty:
                normalized = close.astype(float) / float(close.iloc[0])
                asset_curve = normalized.reindex(combined_index).ffill().bfill()
            else:
                asset_curve = self._build_proxy_curve(
                    combined_index,
                    asset_returns.get(ticker, 0.0),
                )
            contribution_curve = contribution_curve.add(weight * (asset_curve - 1.0), fill_value=0.0)

        portfolio_curve = portfolio_curve.add(contribution_curve, fill_value=0.0)
        portfolio_values = portfolio_curve * total_value
        daily_returns = portfolio_curve.pct_change().fillna(0.0)
        risk_metrics = self.calculate_risk_metrics(daily_returns)

        path = [
            {
                "date": index.strftime("%Y-%m-%d") if hasattr(index, "strftime") else str(index),
                "portfolio_value": float(value),
                "portfolio_return": float(portfolio_curve.loc[index] - 1.0),
            }
            for index, value in portfolio_values.items()
        ]

        return {
            "path": path,
            "risk_metrics": risk_metrics,
            "daily_returns": daily_returns,
            "portfolio_extremes": {
                "highest_value": float(portfolio_values.max()),
                "lowest_value": float(portfolio_values.min()),
                "highest_return": float((portfolio_curve - 1.0).max()),
                "lowest_return": float((portfolio_curve - 1.0).min()),
                "highest_date": portfolio_values.idxmax().strftime("%Y-%m-%d"),
                "lowest_date": portfolio_values.idxmin().strftime("%Y-%m-%d"),
            },
        }

    def _build_macro_summary(self, scenario: Scenario) -> Dict[str, Any]:
        """시나리오 기간의 주요 매크로 지표를 항상 같은 행 구조로 요약한다."""
        items = []
        for indicator in self.MACRO_INDICATORS:
            symbol = indicator["symbol"]
            row = {
                "name": indicator["name"],
                "symbol": symbol,
                "unit": indicator["unit"],
                "start_value": None,
                "end_value": None,
                "change": None,
                "change_pct": None,
                "status": "데이터 없음",
            }
            try:
                data = self._download_history(symbol, scenario, auto_adjust=False)
                if not data.empty:
                    close = self._normalize_price_index(self._extract_close_series(data, symbol).astype(float))
                    scenario_close = close[
                        (close.index <= pd.Timestamp(scenario.end_date))
                    ]
                    if len(scenario_close) >= 2:
                        start_value = float(scenario_close.iloc[0])
                        end_value = float(scenario_close.iloc[-1])
                        change = end_value - start_value
                        row.update(
                            {
                                "start_value": start_value,
                                "end_value": end_value,
                                "change": change,
                                "change_pct": change / start_value if start_value else None,
                                "status": "OK",
                            }
                        )
                        if indicator["unit"] == "yield":
                            row["display_start"] = start_value / 10.0
                            row["display_end"] = end_value / 10.0
                            row["change_bps"] = change * 10.0
            except Exception as exc:
                logger.warning(f"{symbol} 매크로 데이터 조회 실패: {exc}")
            items.append(row)
        return {"items": items}

    def _slice_entry_and_scenario_path(self, close: pd.Series, scenario: Scenario) -> pd.Series:
        """Return previous-close entry point plus scenario-period values."""
        start_date = pd.Timestamp(scenario.start_date)
        end_date = pd.Timestamp(scenario.end_date)
        close = self._normalize_price_index(close.astype(float)).dropna()
        scenario_close = close[(close.index >= start_date) & (close.index <= end_date)]
        if scenario_close.empty:
            return pd.Series(dtype=float)

        entry_candidates = close[close.index < start_date]
        if entry_candidates.empty:
            path = scenario_close
        else:
            path = pd.concat([entry_candidates.tail(1), scenario_close])
        return path[~path.index.duplicated(keep="last")].sort_index()

    def _build_macro_paths(self, scenario: Scenario) -> List[Dict[str, Any]]:
        """Chart-ready macro indicator paths for the scenario window."""
        rows: List[Dict[str, Any]] = []
        for indicator in self.MACRO_INDICATORS:
            symbol = indicator["symbol"]
            try:
                data = self._download_history(symbol, scenario, auto_adjust=False)
                if data.empty:
                    continue

                close = self._extract_close_series(data, symbol)
                path = self._slice_entry_and_scenario_path(close, scenario)
                if path.empty:
                    continue

                display_path = path / 10.0 if indicator["unit"] == "yield" else path
                display_unit = "%" if indicator["unit"] == "yield" else indicator["unit"]
                base_value = float(display_path.iloc[0])

                for index, value in display_path.items():
                    rows.append(
                        {
                            "name": indicator["name"],
                            "symbol": symbol,
                            "date": index.strftime("%Y-%m-%d") if hasattr(index, "strftime") else str(index),
                            "value": float(value),
                            "raw_value": float(path.loc[index]),
                            "unit": display_unit,
                            "indexed_value": float(value / base_value * 100.0) if base_value else None,
                            "status": "OK",
                        }
                    )
            except Exception as exc:
                logger.warning(f"{symbol} macro path fetch failed: {exc}")
        return rows

    def _build_benchmark_comparison(
        self,
        scenario: Scenario,
        total_value: float,
        fx_series: Optional[pd.Series],
    ) -> List[Dict[str, Any]]:
        """주요 벤치마크가 같은 시나리오 기간에 어떻게 움직였는지 비교한다."""
        rows = []
        for benchmark in self.BENCHMARKS:
            symbol = benchmark["symbol"]
            row = {
                "symbol": symbol,
                "name": benchmark["name"],
                "return": None,
                "ending_value": None,
                "status": "데이터 없음",
            }
            try:
                data = self._download_history(symbol, scenario, auto_adjust=True)
                if not data.empty:
                    path = self._build_asset_path_and_extreme(symbol, data, scenario, fx_series=fx_series)
                    if path:
                        ret = float(path["return"])
                        row.update(
                            {
                                "return": ret,
                                "ending_value": float(total_value * (1.0 + ret)),
                                "status": "OK",
                            }
                        )
            except Exception as exc:
                logger.warning(f"{symbol} 벤치마크 조회 실패: {exc}")
            rows.append(row)
        return rows

    def _build_benchmark_price_paths(
        self,
        scenario: Scenario,
        fx_series: Optional[pd.Series],
    ) -> List[Dict[str, Any]]:
        """Chart-ready benchmark paths aligned with asset price paths."""
        rows: List[Dict[str, Any]] = []
        for benchmark in self.BENCHMARKS:
            symbol = benchmark["symbol"]
            try:
                data = self._download_history(symbol, scenario, auto_adjust=True)
                if data.empty:
                    continue

                path = self._build_asset_path_and_extreme(symbol, data, scenario, fx_series=fx_series)
                if not path:
                    continue

                benchmark_rows = self._serialize_asset_price_paths(
                    {symbol: path["path_close"]},
                    {symbol: path["path_quote"]},
                    {symbol: {"quote_currency": path.get("quote_currency")}},
                )
                for row in benchmark_rows:
                    row["name"] = benchmark["name"]
                    row["series_type"] = "Benchmark"
                rows.extend(benchmark_rows)
            except Exception as exc:
                logger.warning(f"{symbol} benchmark path fetch failed: {exc}")
        return rows

    def _build_proxy_asset_path(
        self,
        ticker: str,
        scenario: Scenario,
        fx_series: Optional[pd.Series],
    ) -> Optional[Dict[str, Any]]:
        """누락된 상장 종목을 섹터 대표 ETF의 실제 경로로 대체한다."""
        proxy_info = self._resolve_proxy_etf(ticker)
        proxy_symbol = proxy_info["proxy_symbol"]
        try:
            proxy_data = self._download_history(proxy_symbol, scenario, auto_adjust=True)
            if proxy_data.empty:
                return None
            asset_path = self._build_asset_path_and_extreme(
                ticker,
                proxy_data,
                scenario,
                fx_series=fx_series,
                proxy_symbol=proxy_symbol,
                sector=proxy_info.get("sector"),
            )
            if asset_path:
                asset_path["proxy_info"] = proxy_info
            return asset_path
        except Exception as exc:
            logger.warning(f"{ticker} 프록시 ETF {proxy_symbol} 조회 실패: {exc}")
            return None

    def simulate_scenario(self, portfolio: Dict[str, float], total_value: float, scenario_name: str) -> Dict[str, Any]:
        """
        특정 시나리오에서의 포트폴리오 성과 시뮬레이션
        Args:
            portfolio: {ticker: weight} (e.g. {'AAPL': 0.5, 'MSFT': 0.5})
            total_value: Current portfolio value
            scenario_name: Key in SCENARIOS
        """
        scenario = self.SCENARIOS.get(scenario_name)
        if not scenario:
            return {"error": "Scenario not found"}
            
        # Fetch historical returns for each asset in portfolio
        scenario_returns = {}
        close_series_by_ticker = {}
        quote_series_by_ticker = {}
        asset_metadata = {}
        asset_extremes = {}
        real_data_tickers = []
        proxy_tickers = []
        excluded_tickers = []
        excluded_assets = []
        proxy_assets = []
        proxy_used = False
        fx_used = False
        notes = []
        fx_series = self._get_usdkrw_series(scenario)
        
        for ticker, weight in portfolio.items():
            try:
                data = self._download_history(ticker, scenario, auto_adjust=True)

                if not data.empty:
                    asset_path = self._build_asset_path_and_extreme(
                        ticker,
                        data,
                        scenario,
                        fx_series=fx_series,
                    )
                    if asset_path:
                        scenario_returns[ticker] = float(asset_path["return"])
                        close_series_by_ticker[ticker] = asset_path["path_close"]
                        quote_series_by_ticker[ticker] = asset_path["path_quote"]
                        asset_metadata[ticker] = {
                            "quote_currency": asset_path.get("quote_currency"),
                            "proxy_symbol": asset_path.get("proxy_symbol"),
                            "sector": asset_path.get("sector"),
                        }
                        asset_extremes[ticker] = asset_path["extreme"]
                        fx_used = fx_used or bool(asset_path.get("fx_used"))
                        real_data_tickers.append(ticker)
                        continue

                if self._is_pre_listing_asset(ticker, scenario):
                    scenario_returns[ticker] = 0.0
                    excluded_tickers.append(ticker)
                    excluded_assets.append(
                        {
                            "symbol": ticker,
                            "weight": float(weight),
                            "treatment": "cash",
                            "reason": "시나리오 당시 상장 전이라 현금 비중으로 처리",
                        }
                    )
                    notes.append(f"{ticker}: 시나리오 당시 상장 전이라 해당 비중을 현금(0%)으로 처리")
                    continue

                proxy_path = self._build_proxy_asset_path(ticker, scenario, fx_series)
                if proxy_path:
                    proxy_used = True
                    proxy_tickers.append(ticker)
                    proxy_info = proxy_path.get("proxy_info", {})
                    scenario_returns[ticker] = float(proxy_path["return"])
                    close_series_by_ticker[ticker] = proxy_path["path_close"]
                    quote_series_by_ticker[ticker] = proxy_path["path_quote"]
                    asset_metadata[ticker] = {
                        "quote_currency": proxy_path.get("quote_currency"),
                        "proxy_symbol": proxy_path.get("proxy_symbol"),
                        "sector": proxy_path.get("sector"),
                    }
                    asset_extremes[ticker] = proxy_path["extreme"]
                    fx_used = fx_used or bool(proxy_path.get("fx_used"))
                    proxy_assets.append(
                        {
                            "symbol": ticker,
                            "proxy_symbol": proxy_info.get("proxy_symbol"),
                            "sector": proxy_info.get("sector", "Unknown"),
                            "weight": float(weight),
                            "return": float(proxy_path["return"]),
                        }
                    )
                    notes.append(
                        f"{ticker}: 실데이터 누락으로 {proxy_info.get('sector', 'Unknown')} 섹터 ETF "
                        f"{proxy_info.get('proxy_symbol')} 경로를 사용"
                    )
                    continue

                proxy_used = True
                proxy_tickers.append(ticker)
                proxy_return = self._get_proxy_return(scenario_name, ticker)
                scenario_returns[ticker] = proxy_return
                notes.append(f"{ticker}: 시나리오 프록시 수익률 {proxy_return:.2%} 적용")
                logger.warning(f"{ticker} 데이터 다운로드 실패. 프록시 수익률 적용: {proxy_return:.2%}")
            except Exception as e:
                proxy_used = True
                proxy_tickers.append(ticker)
                proxy_return = self._get_proxy_return(scenario_name, ticker)
                scenario_returns[ticker] = proxy_return
                notes.append(f"{ticker}: 데이터 다운로드 실패로 프록시 수익률 {proxy_return:.2%} 적용")
                logger.warning(f"{ticker} 데이터 다운로드 예외 발생. 프록시 수익률 적용: {e}")

        result = self._calculate_impact(portfolio, total_value, scenario_returns)
        path_result = self._build_path_result(
            portfolio,
            total_value,
            close_series_by_ticker,
            scenario_returns,
            fallback_index=self._scenario_index(scenario),
        )
        result.update(
            {
                "scenario": scenario.name,
                "scenario_key": scenario_name,
                "scenario_type": scenario.scenario_type,
                "scenario_description": scenario.description,
                "price_basis": self.PRICE_BASIS,
                "path": path_result["path"],
                "asset_price_paths": self._serialize_asset_price_paths(
                    close_series_by_ticker,
                    quote_series_by_ticker,
                    asset_metadata,
                ),
                "risk_metrics": path_result["risk_metrics"],
                "asset_extremes": asset_extremes,
                "portfolio_extremes": path_result["portfolio_extremes"],
                "excluded_assets": excluded_assets,
                "proxy_assets": proxy_assets,
                "fx_conversion": {
                    "currency": "KRW",
                    "fx_ticker": self.USDKRW_TICKER,
                    "used": fx_used,
                    "available": fx_series is not None and not fx_series.empty,
                },
                "macro_summary": self._build_macro_summary(scenario),
                "benchmark_comparison": self._build_benchmark_comparison(scenario, total_value, fx_series),
                "benchmark_price_paths": self._build_benchmark_price_paths(scenario, fx_series),
                "macro_paths": self._build_macro_paths(scenario),
            }
        )
        data_quality = self._build_data_quality(
            portfolio,
            real_data_tickers,
            proxy_tickers,
            notes,
            excluded_tickers=excluded_tickers,
        )
        result["data_quality"] = data_quality
        result["risk_classification"] = self.classify_stress_risk(
            result["portfolio_return"],
            result.get("risk_metrics"),
            data_quality,
        )
        if proxy_used:
            result["proxy_used"] = True
            result["notes"] = notes
        else:
            result["proxy_used"] = False
            result["notes"] = []
        return result

    def _calculate_impact(self, portfolio: Dict[str, float], total_value: float, asset_returns: Dict[str, float]) -> Dict[str, Any]:
        """
        자산별 수익률을 바탕으로 포트폴리오 충격 계산
        """
        portfolio_return = 0.0
        details = {}
        
        for ticker, weight in portfolio.items():
            ret = asset_returns.get(ticker, 0.0)
            portfolio_return += weight * ret
            details[ticker] = ret
            
        loss_amount = total_value * portfolio_return
        
        return {
            "scenario": "Custom/Simulation",
            "portfolio_return": portfolio_return,
            "total_loss_amount": loss_amount,
            "details": details
        }

    def simulate_hypothetical_shock(
        self,
        portfolio: Dict[str, float],
        total_value: float,
        shock_return: float,
        asset_shocks: Optional[Dict[str, float]] = None,
        scenario_name: str = "Hypothetical Shock",
    ) -> Dict[str, Any]:
        """전체 포트폴리오 또는 특정 종목에 즉시 충격을 적용한다."""
        asset_shocks = asset_shocks or {}
        asset_returns = {
            ticker: float(asset_shocks.get(ticker, shock_return))
            for ticker in portfolio
        }
        result = self._calculate_impact(portfolio, total_value, asset_returns)
        result.update(
            {
                "scenario": scenario_name,
                "scenario_type": "hypothetical",
                "scenario_description": "User-defined instantaneous market shock",
                "path": [
                    {"date": "start", "portfolio_value": float(total_value), "portfolio_return": 0.0},
                    {
                        "date": "shock",
                        "portfolio_value": float(total_value * (1.0 + result["portfolio_return"])),
                        "portfolio_return": float(result["portfolio_return"]),
                    },
                ],
                "risk_metrics": self.calculate_risk_metrics(pd.Series([result["portfolio_return"]])),
                "data_quality": {
                    "asset_count": len(portfolio),
                    "real_data_count": 0,
                    "proxy_count": 0,
                    "coverage": None,
                    "proxy_weight": 0.0,
                    "level": "SYNTHETIC",
                    "notes": [],
                },
                "proxy_used": False,
                "notes": [],
            }
        )
        result["risk_classification"] = self.classify_stress_risk(
            result["portfolio_return"],
            result.get("risk_metrics"),
            result.get("data_quality"),
        )
        return result

    def simulate_named_scenario(
        self,
        portfolio: Dict[str, float],
        total_value: float,
        scenario_name: str,
    ) -> Dict[str, Any]:
        """역사/가상 시나리오를 같은 진입점에서 실행한다."""
        if scenario_name in self.SCENARIOS:
            return self.simulate_scenario(portfolio, total_value, scenario_name)
        scenario = self.HYPOTHETICAL_SCENARIOS.get(scenario_name)
        if scenario:
            return self.simulate_hypothetical_shock(
                portfolio,
                total_value,
                shock_return=float(scenario.shock_return or 0.0),
                asset_shocks=scenario.asset_shocks,
                scenario_name=scenario.name,
            )
        return {"error": "Scenario not found"}
