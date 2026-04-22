"""
이슈 #7: RVOL(상대거래량) 계산기.

RVOL = today_volume / avg_20d_volume

순수 함수 + OHLCVStore injectable.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ohlcv_store import OHLCVStore


def compute_rvol(today: float, avg20: float | None) -> float | None:
    """
    RVOL 계산. avg20 이 None 이거나 0 이면 None 반환.

    Parameters
    ----------
    today   : 당일 거래량
    avg20   : 20일 평균 거래량 (OHLCVStore.avg_volume 반환값)
    """
    if avg20 is None or avg20 == 0:
        return None
    return round(today / avg20, 4)


def compute_rvol_from_store(
    ticker: str,
    today_volume: float,
    store: "OHLCVStore",
    window: int = 20,
) -> float | None:
    """OHLCVStore 에서 avg_volume 을 조회하여 RVOL 반환."""
    avg = store.avg_volume(ticker, window)
    return compute_rvol(today_volume, avg)
