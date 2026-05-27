"""Supply-flow analysis for growth stock candidates.

Naver Finance is used as the primary source because this project already has a
parser for per-symbol foreign/institutional net flow. pykrx is used as a
fallback when Naver returns no usable records.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Iterable

import pandas as pd

from src.crawling.flow_fetcher import fetch_flow
from src.crawling.flow_signal import detect_reversal

logger = logging.getLogger(__name__)

FlowRecords = list[dict]
NaverFlowFetcher = Callable[[str], FlowRecords]
PykrxFlowFetcher = Callable[[str], object]


@dataclass
class SupplyFlowAnalysis:
    """Foreign/institutional supply-flow signal for one KR stock."""

    ticker: str
    source: str = "none"
    flow_unit: str = ""
    score: float = 0.0
    latest_foreign: int = 0
    latest_institution: int = 0
    foreign_5d_sum: int = 0
    institution_5d_sum: int = 0
    smart_money_5d_sum: int = 0
    positive_days_5d: int = 0
    reversal_types: list[str] = field(default_factory=list)
    reason: str = ""


class SupplyFlowProvider:
    """Fetch and score foreign/institutional flow with Naver -> pykrx fallback."""

    def __init__(
        self,
        *,
        naver_fetcher: NaverFlowFetcher | None = None,
        pykrx_fetcher: PykrxFlowFetcher | None = None,
        lookback: int = 5,
    ) -> None:
        self._naver_fetcher = naver_fetcher or fetch_flow
        self._pykrx_fetcher = pykrx_fetcher or self._fetch_pykrx_flow
        self.lookback = max(3, int(lookback))

    def analyze(self, symbol: str) -> SupplyFlowAnalysis:
        ticker = _normalize_kr_ticker(symbol)
        if not ticker:
            return SupplyFlowAnalysis(ticker=str(symbol), reason="KR ticker unavailable")

        records = self._safe_fetch_naver(ticker)
        source = "naver" if records else "none"
        if not records:
            records = self._records_from_pykrx(self._safe_fetch_pykrx(ticker))
            source = "pykrx" if records else "none"
        flow_unit = "주" if source == "naver" else "KRW" if source == "pykrx" else ""

        normalized = _normalize_records(records)
        if not normalized:
            return SupplyFlowAnalysis(
                ticker=ticker,
                source=source,
                flow_unit=flow_unit,
                reason="수급 데이터 없음",
            )

        window = normalized[: self.lookback]
        latest = normalized[0]
        foreign_sum = sum(int(record.get("foreign", 0)) for record in window)
        institution_sum = sum(int(record.get("institution", 0)) for record in window)
        smart_money_sum = foreign_sum + institution_sum
        positive_days = sum(
            1
            for record in window
            if int(record.get("foreign", 0)) + int(record.get("institution", 0)) > 0
        )
        reversal_types = [
            str(signal.get("reversal_type"))
            for signal in detect_reversal(normalized, lookback=self.lookback)
            if signal.get("reversal_type")
        ]
        score = _score_supply_flow(
            latest_foreign=int(latest.get("foreign", 0)),
            latest_institution=int(latest.get("institution", 0)),
            smart_money_sum=smart_money_sum,
            positive_days=positive_days,
            reversal_types=reversal_types,
            lookback=self.lookback,
        )

        return SupplyFlowAnalysis(
            ticker=ticker,
            source=source,
            flow_unit=flow_unit,
            score=score,
            latest_foreign=int(latest.get("foreign", 0)),
            latest_institution=int(latest.get("institution", 0)),
            foreign_5d_sum=foreign_sum,
            institution_5d_sum=institution_sum,
            smart_money_5d_sum=smart_money_sum,
            positive_days_5d=positive_days,
            reversal_types=reversal_types,
            reason=_build_reason(
                score,
                smart_money_sum,
                positive_days,
                reversal_types,
                source,
                flow_unit,
            ),
        )

    def _safe_fetch_naver(self, ticker: str) -> FlowRecords:
        try:
            return self._naver_fetcher(ticker) or []
        except Exception as exc:
            logger.debug("naver flow fetch failed for %s: %s", ticker, exc)
            return []

    def _safe_fetch_pykrx(self, ticker: str) -> object:
        try:
            return self._pykrx_fetcher(ticker)
        except Exception as exc:
            logger.debug("pykrx flow fetch failed for %s: %s", ticker, exc)
            return []

    def _fetch_pykrx_flow(self, ticker: str) -> pd.DataFrame:
        stock = importlib.import_module("pykrx.stock")
        end = date.today()
        start = end - timedelta(days=40)
        return stock.get_market_trading_value_by_date(
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            ticker,
        )

    @staticmethod
    def _records_from_pykrx(raw: object) -> FlowRecords:
        if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
            return []

        foreign_col = _pick_column(raw.columns, ["외국인합계", "외국인"])
        institution_col = _pick_column(raw.columns, ["기관합계", "기관"])
        if foreign_col is None and institution_col is None:
            return []

        frame = raw.copy()
        frame.index = pd.to_datetime(frame.index, errors="coerce")
        frame = frame[~frame.index.isna()].sort_index(ascending=False)

        records: FlowRecords = []
        for idx, row in frame.iterrows():
            records.append(
                {
                    "date": idx.strftime("%Y.%m.%d"),
                    "foreign": _safe_int(row.get(foreign_col, 0)) if foreign_col else 0,
                    "institution": _safe_int(row.get(institution_col, 0))
                    if institution_col
                    else 0,
                }
            )
        return records


def _normalize_kr_ticker(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    if raw.endswith(".KQ") or raw.endswith(".KS"):
        raw = raw[:-3]
    return raw.zfill(6) if raw.isdigit() else ""


def _normalize_records(records: Iterable[dict]) -> FlowRecords:
    normalized: FlowRecords = []
    for record in records or []:
        date_text = str(record.get("date", "")).strip()
        normalized.append(
            {
                "date": date_text,
                "foreign": _safe_int(record.get("foreign", 0)),
                "institution": _safe_int(record.get("institution", 0)),
            }
        )
    return normalized


def _score_supply_flow(
    *,
    latest_foreign: int,
    latest_institution: int,
    smart_money_sum: int,
    positive_days: int,
    reversal_types: list[str],
    lookback: int,
) -> float:
    score = 0.0
    latest_sum = latest_foreign + latest_institution
    if latest_sum > 0:
        score += 0.2
    elif latest_sum < 0:
        score -= 0.15

    if smart_money_sum > 0:
        score += 0.35
    elif smart_money_sum < 0:
        score -= 0.3

    if positive_days >= lookback:
        score += 0.3
    elif positive_days >= max(3, lookback - 1):
        score += 0.2
    elif positive_days <= 1:
        score -= 0.15

    buy_reversals = [item for item in reversal_types if "매수전환" in item]
    sell_reversals = [item for item in reversal_types if "매도전환" in item]
    if buy_reversals:
        score += 0.35
    if sell_reversals:
        score -= 0.35

    return round(max(-0.5, min(1.0, score)), 2)


def _build_reason(
    score: float,
    smart_money_sum: int,
    positive_days: int,
    reversal_types: list[str],
    source: str,
    flow_unit: str,
) -> str:
    parts = []
    if reversal_types:
        parts.append(",".join(reversal_types))
    unit_suffix = f" {flow_unit}" if flow_unit else ""
    parts.append(f"5일 수급 {smart_money_sum:+,d}{unit_suffix}")
    parts.append(f"양수 {positive_days}일")
    parts.append(f"source={source}")
    parts.append(f"score={score:.1f}")
    return ", ".join(parts)


def _pick_column(columns, candidates: list[str]) -> str | None:
    names = [str(column) for column in columns]
    for candidate in candidates:
        if candidate in names:
            return candidate
    for candidate in candidates:
        for name in names:
            if candidate in name:
                return name
    return None


def _safe_int(value) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(str(value).replace(",", "").replace("+", "").strip()))
    except (TypeError, ValueError):
        return 0
