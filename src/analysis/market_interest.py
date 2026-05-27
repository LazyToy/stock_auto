"""Market-wide candidate discovery for growth stock screening.

The provider scans the live market first, narrows the universe by liquidity and
current attention, then fetches short daily histories only for that smaller
pool. Financial statements are intentionally left to ``growth_stock_finder`` so
expensive fundamentals are requested only after this market-interest pass.
"""

from __future__ import annotations

import importlib
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)


MarketFetcher = Callable[[], pd.DataFrame]
HistoryFetcher = Callable[[str], pd.DataFrame]


@dataclass
class MarketInterestCandidate:
    """A stock that has accumulated market attention over recent days/weeks."""

    symbol: str
    name: str
    market: str
    sector: str = "Unknown"
    interest_score: float = 0.0
    current_price: Optional[float] = None
    price_currency: str = ""
    current_change: Optional[float] = None
    traded_value: Optional[float] = None
    market_cap: Optional[float] = None
    momentum_5d: Optional[float] = None
    momentum_20d: Optional[float] = None
    momentum_window: Optional[float] = None
    interest_window_days: int = 20
    volume_ratio_20d: Optional[float] = None
    high_proximity_120d: Optional[float] = None
    overheat_penalty: float = 0.0
    sector_rank: Optional[int] = None
    sector_count: int = 0
    sector_percentile: Optional[float] = None
    reason: str = ""


class MarketInterestCandidateProvider:
    """Build growth-stock candidates from live market-wide data."""

    def __init__(
        self,
        *,
        kr_market_fetcher: MarketFetcher | None = None,
        us_market_fetcher: MarketFetcher | None = None,
        history_fetcher: HistoryFetcher | None = None,
    ) -> None:
        self._kr_market_fetcher = kr_market_fetcher or self._fetch_kr_market
        self._us_market_fetcher = us_market_fetcher or self._fetch_us_market
        self._history_fetcher = history_fetcher or self._fetch_history

    def build_candidates(
        self,
        market: str,
        *,
        limit: int = 80,
        prefilter_limit: int = 200,
        interest_window_days: int = 20,
    ) -> list[MarketInterestCandidate]:
        """Return top market-interest candidates for ``market``.

        ``prefilter_limit`` controls how many liquid/currently active names get
        short history calls. ``limit`` controls how many symbols proceed to
        financial screening.
        """
        market = market.upper()
        interest_window_days = max(5, min(120, int(interest_window_days)))
        raw = self._kr_market_fetcher() if market == "KR" else self._us_market_fetcher()
        normalized = self._normalize_market_frame(raw, market)
        if normalized.empty:
            return []

        pool = normalized[
            (normalized["symbol"].astype(str).str.len() > 0)
            & (normalized["close"] > 0)
            & (normalized["traded_value"] > 0)
        ].copy()
        if pool.empty:
            return []

        pool["_snapshot_score"] = pool.apply(self._snapshot_score, axis=1)
        pool = pool.sort_values("_snapshot_score", ascending=False).head(prefilter_limit)

        candidates: list[MarketInterestCandidate] = []
        for record in pool.to_dict("records"):
            symbol = str(record["symbol"])
            metrics = self._history_metrics(symbol, interest_window_days)
            overheat_penalty = self._overheat_penalty(record, metrics)
            score = self._interest_score(record, metrics, overheat_penalty)
            candidate = MarketInterestCandidate(
                symbol=symbol,
                name=str(record.get("name") or symbol),
                market=market,
                sector=str(record.get("sector") or "Unknown"),
                interest_score=score,
                current_price=_optional_float(record.get("close")),
                price_currency=str(record.get("price_currency") or ("KRW" if market == "KR" else "USD")),
                current_change=_optional_float(record.get("current_change")),
                traded_value=_optional_float(record.get("traded_value")),
                market_cap=_optional_float(record.get("market_cap")),
                momentum_5d=metrics.get("momentum_5d"),
                momentum_20d=metrics.get("momentum_20d"),
                momentum_window=metrics.get("momentum_window"),
                interest_window_days=interest_window_days,
                volume_ratio_20d=metrics.get("volume_ratio_20d"),
                high_proximity_120d=metrics.get("high_proximity_120d"),
                overheat_penalty=overheat_penalty,
                reason=self._build_reason(metrics, interest_window_days, overheat_penalty),
            )
            candidates.append(candidate)

        candidates.sort(key=lambda item: item.interest_score, reverse=True)
        self._annotate_sector_ranks(candidates)
        return candidates[:limit]

    @staticmethod
    def _annotate_sector_ranks(candidates: list[MarketInterestCandidate]) -> None:
        """후보군 안에서 섹터별 상대 순위를 붙인다."""
        by_sector: dict[str, list[MarketInterestCandidate]] = {}
        for candidate in candidates:
            by_sector.setdefault(candidate.sector or "Unknown", []).append(candidate)

        for sector_candidates in by_sector.values():
            sector_candidates.sort(key=lambda item: item.interest_score, reverse=True)
            count = len(sector_candidates)
            for index, candidate in enumerate(sector_candidates, start=1):
                candidate.sector_rank = index
                candidate.sector_count = count
                candidate.sector_percentile = (
                    1.0 if count == 1 else round(1.0 - ((index - 1) / (count - 1)), 4)
                )

    @staticmethod
    def _fetch_kr_market() -> pd.DataFrame:
        fdr = importlib.import_module("FinanceDataReader")
        df = fdr.StockListing("KRX")
        return df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy()

    @staticmethod
    def _fetch_us_market() -> pd.DataFrame:
        from src.crawling.market_trend import fetch_us

        return fetch_us(min_volume_usd=1_000_000, limit=2000)

    @staticmethod
    def _fetch_history(symbol: str) -> pd.DataFrame:
        yf = importlib.import_module("yfinance")
        return yf.Ticker(symbol).history(period="6mo", interval="1d")

    def _normalize_market_frame(self, df: pd.DataFrame, market: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        if market == "KR":
            return self._normalize_kr_frame(df)
        return self._normalize_us_frame(df)

    def _normalize_kr_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        if "Market" in work.columns:
            work = work[work["Market"].isin(["KOSPI", "KOSDAQ"])].copy()

        codes = work.get("Code", pd.Series(dtype=str)).astype(str).str.zfill(6)
        markets = work.get("Market", pd.Series("", index=work.index)).astype(str)
        suffixes = markets.map({"KOSPI": ".KS", "KOSDAQ": ".KQ"}).fillna("")
        sectors = self._load_cached_kr_sectors(codes.tolist())

        return pd.DataFrame(
            {
                "symbol": codes + suffixes,
                "name": work.get("Name", codes).astype(str),
                "sector": [sectors.get(code, "Unknown") for code in codes],
                "close": _numeric(work.get("Close", 0)),
                "price_currency": "KRW",
                "current_change": _numeric(work.get("ChagesRatio", 0)),
                "traded_value": _numeric(work.get("Amount", 0)),
                "market_cap": _numeric(work.get("Marcap", 0)),
                "volume": _numeric(work.get("Volume", 0)),
            }
        )

    @staticmethod
    def _normalize_us_frame(df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        tickers = work.get("ticker", work.get("name", pd.Series(dtype=str))).astype(str)
        names = work.get("name", work.get("description", tickers)).astype(str)
        return pd.DataFrame(
            {
                "symbol": tickers.str.upper(),
                "name": names,
                "sector": work.get("sector", pd.Series("Unknown", index=work.index)).astype(str),
                "close": _numeric(work.get("close", 0)),
                "price_currency": "USD",
                "current_change": _numeric(work.get("change", 0)),
                "traded_value": _numeric(work.get("volume_value", 0)),
                "market_cap": _numeric(work.get("market_cap", 0)),
                "volume": _numeric(work.get("volume", 0)),
            }
        )

    @staticmethod
    def _load_cached_kr_sectors(codes: list[str]) -> dict[str, str]:
        path = Path("sector_map_kr.json")
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return {}
        return {str(code).zfill(6): str(data.get(str(code).zfill(6), "Unknown")) for code in codes}

    def _history_metrics(self, symbol: str, interest_window_days: int) -> dict[str, Optional[float]]:
        try:
            history = self._history_fetcher(symbol)
        except Exception as exc:
            logger.debug("history fetch failed for %s: %s", symbol, exc)
            return {}
        if history is None or history.empty or "Close" not in history.columns:
            return {}

        close = pd.to_numeric(history["Close"], errors="coerce").dropna()
        if close.empty:
            return {}

        volume = (
            pd.to_numeric(history["Volume"], errors="coerce").dropna()
            if "Volume" in history.columns
            else pd.Series(dtype=float)
        )
        high = (
            pd.to_numeric(history["High"], errors="coerce").dropna()
            if "High" in history.columns
            else close
        )
        latest_close = float(close.iloc[-1])
        return {
            "momentum_5d": _pct_change(close, 5),
            "momentum_20d": _pct_change(close, 20),
            "momentum_window": _pct_change(close, interest_window_days),
            "volume_ratio_20d": _volume_ratio(volume),
            "high_proximity_120d": _high_proximity(latest_close, high),
        }

    @staticmethod
    def _snapshot_score(record: pd.Series) -> float:
        traded_value = max(float(record.get("traded_value") or 0), 0.0)
        market_cap = max(float(record.get("market_cap") or 0), 0.0)
        change = float(record.get("current_change") or 0)
        return math.log10(traded_value + 1) + math.log10(market_cap + 1) * 0.05 + max(change, 0) * 0.08

    @staticmethod
    def _interest_score(
        record: dict,
        metrics: dict[str, Optional[float]],
        overheat_penalty: float = 0.0,
    ) -> float:
        traded_value = max(float(record.get("traded_value") or 0), 0.0)
        current_change = float(record.get("current_change") or 0)
        momentum_5d = metrics.get("momentum_5d")
        momentum_window = metrics.get("momentum_window")
        volume_ratio = metrics.get("volume_ratio_20d")
        high_proximity = metrics.get("high_proximity_120d")

        liquidity_points = _clamp(math.log10(traded_value + 1) - 7.0, 0.0, 3.0)
        momentum_window_points = _clamp((momentum_window or 0.0) / 5.0, -2.0, 4.0)
        momentum_5_points = _clamp((momentum_5d or 0.0) / 3.0, -1.0, 2.0)
        volume_points = _clamp(((volume_ratio or 1.0) - 1.0) * 0.9, 0.0, 3.0)
        current_points = _clamp(current_change, -5.0, 8.0) * 0.1
        high_points = _clamp(high_proximity or 0.0, 0.0, 1.0)

        score = (
            liquidity_points
            + momentum_window_points
            + momentum_5_points
            + volume_points
            + current_points
            + high_points
            + overheat_penalty
        )
        return round(max(0.0, score), 2)

    @staticmethod
    def _overheat_penalty(record: dict, metrics: dict[str, Optional[float]]) -> float:
        """단발 급등/거래량 폭발 후보를 누적 관심 후보보다 낮게 본다."""
        current_change = float(record.get("current_change") or 0.0)
        momentum_5d = metrics.get("momentum_5d") or 0.0
        momentum_window = metrics.get("momentum_window") or 0.0
        volume_ratio = metrics.get("volume_ratio_20d") or 1.0

        penalty = 0.0
        if current_change >= 20:
            penalty -= 3.0
        elif current_change >= 12:
            penalty -= 1.5

        if momentum_5d >= 25:
            penalty -= 2.0
        elif momentum_5d >= 15:
            penalty -= 1.0

        if current_change >= 12 and volume_ratio >= 3.0:
            penalty -= 1.0

        if momentum_window > 0 and momentum_5d >= momentum_window * 0.75:
            penalty -= 1.0

        return round(penalty, 2)

    @staticmethod
    def _build_reason(
        metrics: dict[str, Optional[float]],
        interest_window_days: int,
        overheat_penalty: float = 0.0,
    ) -> str:
        parts = []
        if metrics.get("momentum_window") is not None:
            parts.append(f"{interest_window_days}d momentum {metrics['momentum_window']:.1f}%")
        if metrics.get("volume_ratio_20d") is not None:
            parts.append(f"5d/20d volume {metrics['volume_ratio_20d']:.1f}x")
        if metrics.get("high_proximity_120d") is not None:
            parts.append(f"near high {metrics['high_proximity_120d']:.0%}")
        if overheat_penalty < 0:
            parts.append(f"overheat penalty {overheat_penalty:.1f}")
        return ", ".join(parts) if parts else "market snapshot only"


def _numeric(value) -> pd.Series:
    if isinstance(value, pd.Series):
        return pd.to_numeric(value, errors="coerce").fillna(0.0)
    return pd.Series(value, dtype=float)


def _optional_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _pct_change(close: pd.Series, periods: int) -> Optional[float]:
    if len(close) <= periods:
        return None
    base = float(close.iloc[-periods - 1])
    if base == 0:
        return None
    return (float(close.iloc[-1]) / base - 1.0) * 100.0


def _volume_ratio(volume: pd.Series) -> Optional[float]:
    if len(volume) < 10:
        return None
    recent = float(volume.tail(5).mean())
    if len(volume) >= 25:
        base_series = volume.iloc[-25:-5]
    else:
        base_series = volume.iloc[:-5]
    base = float(base_series.mean()) if not base_series.empty else 0.0
    if base <= 0:
        return None
    return recent / base


def _high_proximity(latest_close: float, high: pd.Series) -> Optional[float]:
    if high.empty:
        return None
    period_high = float(high.tail(120).max())
    if period_high <= 0:
        return None
    return latest_close / period_high


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
