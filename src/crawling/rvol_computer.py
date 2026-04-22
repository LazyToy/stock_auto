"""
RVOL(relative volume) helpers for crawling signals.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.crawling.ohlcv_store import OHLCVStore


def compute_rvol(today: float, avg20: float | None) -> float | None:
    if avg20 is None or avg20 == 0:
        return None
    return round(today / avg20, 4)


def compute_rvol_from_store(
    ticker: str,
    today_volume: float,
    store: "OHLCVStore",
    window: int = 20,
) -> float | None:
    avg = store.avg_volume(ticker, window)
    return compute_rvol(today_volume, avg)
