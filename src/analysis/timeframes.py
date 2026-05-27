"""멀티타임프레임 OHLCV 데이터 수집기.

PR-06 범위:
    - 한 종목의 5분봉, 1시간봉, 일봉 데이터를 동일 계약으로 수집한다.
    - 일부 timeframe 수집 실패가 전체 dataset 실패로 번지지 않게 격리한다.
    - 네트워크/API 세부 구현은 기존 KISAPIClient와 yfinance fallback에 위임한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from importlib import import_module
from typing import Any, Callable, Protocol, cast

import pandas as pd

from src.analysis.ohlcv import (
    REQUIRED_COLUMNS,
    normalize_ohlcv_frame,
    stock_prices_to_ohlcv,
    validate_ohlcv_frame,
)
from src.data.models import StockPrice

DEFAULT_MINUTE_COUNT: int = 100
DEFAULT_DAILY_LOOKBACK_DAYS: int = 365
YFINANCE_DAILY_PERIOD: str = "1y"


class PriceHistoryClient(Protocol):
    """KIS 가격 조회 client가 제공해야 하는 최소 계약."""

    def get_minute_price(
        self,
        symbol: str,
        interval: int = 1,
        count: int = 100,
        exchange: str = "NASD",
    ) -> list[StockPrice]:
        """분봉 데이터를 반환한다."""

    def get_daily_price_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[StockPrice]:
        """일봉 데이터를 반환한다."""


class Timeframe(str, Enum):
    """Smart Money 분석에서 사용하는 표준 timeframe."""

    MINUTE_5 = "5m"
    HOUR_1 = "1h"
    DAY_1 = "1d"


@dataclass(frozen=True)
class TimeframeData:
    """단일 timeframe 수집 결과."""

    timeframe: Timeframe
    data: pd.DataFrame | None = None
    error: str | None = None
    source: str = ""

    @property
    def is_success(self) -> bool:
        """OHLCV DataFrame이 있고 error가 없으면 성공으로 본다."""
        return self.error is None and self.data is not None


@dataclass
class MultiTimeframeDataset:
    """한 종목의 멀티타임프레임 OHLCV 묶음."""

    symbol: str
    market: str
    exchange: str = "NASD"
    timeframes: dict[Timeframe, TimeframeData] = field(default_factory=dict)

    def get(self, timeframe: Timeframe | str) -> TimeframeData:
        """timeframe 결과를 반환한다. 없으면 실패 결과를 반환한다."""
        key = _coerce_timeframe(timeframe)
        return self.timeframes.get(
            key,
            TimeframeData(
                timeframe=key,
                error=f"missing_timeframe:{key.value}",
                source="dataset",
            ),
        )

    def successful_ohlcv(self) -> dict[str, pd.DataFrame]:
        """성공한 timeframe의 OHLCV DataFrame만 문자열 키 dict로 반환한다."""
        frames: dict[str, pd.DataFrame] = {}
        for timeframe, result in self.timeframes.items():
            if result.is_success and result.data is not None:
                frames[timeframe.value] = result.data.copy()
        return frames


YFinanceHistoryFetcher = Callable[[str, str, str], pd.DataFrame]
ApiClientFactory = Callable[[str], PriceHistoryClient]


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """OHLCV DataFrame을 지정한 pandas resample rule로 집계한다."""
    if not rule:
        raise ValueError("resample rule이 비어 있습니다.")

    normalized = normalize_ohlcv_frame(df)
    aggregated = normalized.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    aggregated = aggregated.dropna(subset=["open", "high", "low", "close"])
    return cast(pd.DataFrame, aggregated)


class MultiTimeframeFetcher:
    """KIS/yfinance를 조합해 한 종목의 5m, 1h, 1d OHLCV를 수집한다."""

    def __init__(
        self,
        api_client_factory: ApiClientFactory | None = None,
        yfinance_history_fetcher: YFinanceHistoryFetcher | None = None,
        minute_count: int = DEFAULT_MINUTE_COUNT,
        daily_lookback_days: int = DEFAULT_DAILY_LOOKBACK_DAYS,
        yfinance_daily_period: str = YFINANCE_DAILY_PERIOD,
    ) -> None:
        """외부 의존성을 주입받아 네트워크 호출을 테스트에서 격리한다."""
        if minute_count < 1:
            raise ValueError("minute_count는 1 이상이어야 합니다.")
        if daily_lookback_days < 1:
            raise ValueError("daily_lookback_days는 1 이상이어야 합니다.")

        if not isinstance(yfinance_daily_period, str) or not yfinance_daily_period.strip():
            raise ValueError("yfinance_daily_period 값은 비어 있으면 안 됩니다.")

        self._api_client_factory = api_client_factory or _default_api_client_factory
        self._yfinance_history_fetcher = yfinance_history_fetcher or _fetch_yfinance_history
        self._minute_count = minute_count
        self._daily_lookback_days = daily_lookback_days
        self._yfinance_daily_period = yfinance_daily_period.strip()

    def fetch_symbol(
        self,
        symbol: str,
        market: str = "KR",
        exchange: str = "NASD",
    ) -> MultiTimeframeDataset:
        """symbol의 5m/1h/1d OHLCV를 수집하고 timeframe별 실패를 격리한다."""
        clean_symbol = _validate_symbol(symbol)
        clean_market = _validate_market(market)
        clean_exchange = _validate_exchange(exchange)
        client = self._api_client_factory(clean_market)

        dataset = MultiTimeframeDataset(
            symbol=clean_symbol,
            market=clean_market,
            exchange=clean_exchange,
        )
        if clean_market == "KR":
            dataset.timeframes = self._fetch_kr_timeframes(client, clean_symbol, clean_exchange)
        else:
            dataset.timeframes = self._fetch_us_timeframes(client, clean_symbol, clean_exchange)
        return dataset

    def _fetch_kr_timeframes(
        self,
        client: PriceHistoryClient,
        symbol: str,
        exchange: str,
    ) -> dict[Timeframe, TimeframeData]:
        """KR 1분 원천과 일봉 API로 timeframe 결과를 만든다."""
        results: dict[Timeframe, TimeframeData] = {}
        try:
            one_minute = self._fetch_minute_frame(client, symbol, 1, exchange, "kis:kr:1m")
            results[Timeframe.MINUTE_5] = _success(
                Timeframe.MINUTE_5,
                resample_ohlcv(one_minute, "5min"),
                "kis:kr:1m:resample:5min",
            )
            results[Timeframe.HOUR_1] = _success(
                Timeframe.HOUR_1,
                resample_ohlcv(one_minute, "60min"),
                "kis:kr:1m:resample:60min",
            )
        except Exception as exc:
            error = _format_error(exc)
            results[Timeframe.MINUTE_5] = _failure(Timeframe.MINUTE_5, error, "kis:kr:1m")
            results[Timeframe.HOUR_1] = _failure(Timeframe.HOUR_1, error, "kis:kr:1m")

        results[Timeframe.DAY_1] = self._safe_fetch_daily_kr(client, symbol)
        return results

    def _fetch_us_timeframes(
        self,
        client: PriceHistoryClient,
        symbol: str,
        exchange: str,
    ) -> dict[Timeframe, TimeframeData]:
        """US KIS 분봉과 yfinance 일봉 fallback으로 timeframe 결과를 만든다."""
        results: dict[Timeframe, TimeframeData] = {}
        five_minute = self._safe_fetch_us_minute(client, symbol, 5, exchange, Timeframe.MINUTE_5)
        results[Timeframe.MINUTE_5] = five_minute
        results[Timeframe.HOUR_1] = self._fetch_us_hourly(client, symbol, exchange, five_minute)
        results[Timeframe.DAY_1] = self._safe_fetch_daily_yfinance(symbol)
        return results

    def _fetch_us_hourly(
        self,
        client: PriceHistoryClient,
        symbol: str,
        exchange: str,
        five_minute: TimeframeData,
    ) -> TimeframeData:
        """US 60분 API를 우선 사용하고 실패 시 5분봉 resample로 대체한다."""
        hourly = self._safe_fetch_us_minute(client, symbol, 60, exchange, Timeframe.HOUR_1)
        if hourly.is_success:
            return hourly
        if five_minute.data is None:
            return hourly
        try:
            return _success(
                Timeframe.HOUR_1,
                resample_ohlcv(five_minute.data, "60min"),
                "kis:us:5m:resample:60min",
            )
        except Exception as exc:
            return _failure(Timeframe.HOUR_1, _format_error(exc), "kis:us:5m:resample:60min")

    def _safe_fetch_us_minute(
        self,
        client: PriceHistoryClient,
        symbol: str,
        interval: int,
        exchange: str,
        timeframe: Timeframe,
    ) -> TimeframeData:
        """US 분봉 조회 실패를 TimeframeData.error로 변환한다."""
        source = f"kis:us:{interval}m"
        try:
            frame = self._fetch_minute_frame(client, symbol, interval, exchange, source)
            return _success(timeframe, frame, source)
        except Exception as exc:
            return _failure(timeframe, _format_error(exc), source)

    def _safe_fetch_daily_kr(
        self,
        client: PriceHistoryClient,
        symbol: str,
    ) -> TimeframeData:
        """KR 일봉 조회 실패를 TimeframeData.error로 변환한다."""
        try:
            end = date.today()
            start = end - timedelta(days=self._daily_lookback_days)
            prices = client.get_daily_price_history(
                symbol,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
            )
            frame = _normalize_fetched_frame(stock_prices_to_ohlcv(prices))
            return _success(Timeframe.DAY_1, frame, "kis:kr:daily")
        except Exception as exc:
            return _failure(Timeframe.DAY_1, _format_error(exc), "kis:kr:daily")

    def _safe_fetch_daily_yfinance(self, symbol: str) -> TimeframeData:
        """yfinance 일봉 fallback 실패를 TimeframeData.error로 변환한다."""
        source = "yfinance:history:1d"
        try:
            raw = self._yfinance_history_fetcher(symbol, self._yfinance_daily_period, "1d")
            frame = _normalize_fetched_frame(raw)
            return _success(Timeframe.DAY_1, frame, source)
        except Exception as exc:
            return _failure(Timeframe.DAY_1, _format_error(exc), source)

    def _fetch_minute_frame(
        self,
        client: PriceHistoryClient,
        symbol: str,
        interval: int,
        exchange: str,
        source: str,
    ) -> pd.DataFrame:
        """KIS 분봉 StockPrice 리스트를 검증된 OHLCV DataFrame으로 변환한다."""
        prices = client.get_minute_price(
            symbol,
            interval=interval,
            count=self._minute_count,
            exchange=exchange,
        )
        return _normalize_fetched_frame(stock_prices_to_ohlcv(prices), source=source)


def fetch_symbol(
    symbol: str,
    market: str = "KR",
    exchange: str = "NASD",
) -> MultiTimeframeDataset:
    """기본 의존성으로 한 종목의 멀티타임프레임 OHLCV를 수집한다."""
    return MultiTimeframeFetcher().fetch_symbol(symbol, market=market, exchange=exchange)


def _success(timeframe: Timeframe, frame: pd.DataFrame, source: str) -> TimeframeData:
    """성공 결과를 만들기 전 표준 OHLCV 검증을 수행한다."""
    normalized = _normalize_fetched_frame(frame, source=source)
    return TimeframeData(timeframe=timeframe, data=normalized, source=source)


def _failure(timeframe: Timeframe, error: str, source: str) -> TimeframeData:
    """실패 결과를 표준 형태로 만든다."""
    return TimeframeData(timeframe=timeframe, error=error, source=source)


def _normalize_fetched_frame(df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    """수집된 DataFrame을 표준 OHLCV로 정규화하고 유효성을 검증한다."""
    if df.empty and not isinstance(df.index, pd.DatetimeIndex):
        df = stock_prices_to_ohlcv([])
    normalized = normalize_ohlcv_frame(df)
    is_valid, errors = validate_ohlcv_frame(normalized)
    if not is_valid:
        prefix = f"{source}:" if source else ""
        raise ValueError(prefix + ",".join(errors))
    projected = normalized.loc[:, list(REQUIRED_COLUMNS)].copy()
    return cast(pd.DataFrame, projected)


def _fetch_yfinance_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """yfinance에서 일봉 history를 조회한다."""
    try:
        yf = cast(Any, import_module("yfinance"))
    except ImportError as exc:
        raise RuntimeError("yfinance 패키지를 사용할 수 없습니다.") from exc

    ticker = yf.Ticker(symbol)
    return cast(pd.DataFrame, ticker.history(period=period, interval=interval))


def _default_api_client_factory(market: str) -> PriceHistoryClient:
    """기본 KISAPIClient를 생성한다."""
    api_client_module: Any = import_module("src.data.api_client")
    kis_api_client = api_client_module.KISAPIClient

    return cast(PriceHistoryClient, kis_api_client(market=market))


def _validate_symbol(symbol: object) -> str:
    """symbol 입력을 검증하고 공백을 제거한다."""
    if symbol is None:
        raise ValueError("symbol이 None입니다.")
    if not isinstance(symbol, str):
        raise ValueError("symbol은 문자열이어야 합니다.")
    clean_symbol = symbol.strip()
    if not clean_symbol:
        raise ValueError("symbol이 비어 있습니다.")
    return clean_symbol


def _validate_market(market: object) -> str:
    """market 입력을 KR 또는 US로 제한한다."""
    if market is None:
        raise ValueError("market이 None입니다.")
    if not isinstance(market, str):
        raise ValueError("market은 문자열이어야 합니다.")
    clean_market = market.strip().upper()
    if clean_market not in {"KR", "US"}:
        raise ValueError("market은 'KR' 또는 'US'만 지원합니다.")
    return clean_market


def _validate_exchange(exchange: object) -> str:
    """exchange 입력을 검증하고 공백을 제거한다."""
    if exchange is None:
        raise ValueError("exchange가 None입니다.")
    if not isinstance(exchange, str):
        raise ValueError("exchange는 문자열이어야 합니다.")
    clean_exchange = exchange.strip().upper()
    if not clean_exchange:
        raise ValueError("exchange가 비어 있습니다.")
    return clean_exchange


def _coerce_timeframe(timeframe: Timeframe | str) -> Timeframe:
    """문자열 timeframe을 Timeframe enum으로 변환한다."""
    if isinstance(timeframe, Timeframe):
        return timeframe
    try:
        return Timeframe(timeframe)
    except ValueError as exc:
        raise ValueError(f"지원하지 않는 timeframe입니다: {timeframe}") from exc


def _format_error(exc: Exception) -> str:
    """예외를 사용자에게 남길 짧은 error 문자열로 변환한다."""
    return str(exc) or exc.__class__.__name__


__all__ = [
    "MultiTimeframeDataset",
    "MultiTimeframeFetcher",
    "Timeframe",
    "TimeframeData",
    "fetch_symbol",
    "resample_ohlcv",
]
