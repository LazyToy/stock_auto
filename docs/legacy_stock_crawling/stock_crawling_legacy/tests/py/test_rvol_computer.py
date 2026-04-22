"""이슈 #7: RVOL 계산기 단위 테스트."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def test_compute_rvol_basic():
    from rvol_computer import compute_rvol
    assert compute_rvol(today=300, avg20=100) == 3.0

def test_compute_rvol_zero_avg_returns_none():
    from rvol_computer import compute_rvol
    assert compute_rvol(today=100, avg20=0) is None

def test_compute_rvol_none_avg_returns_none():
    from rvol_computer import compute_rvol
    assert compute_rvol(today=100, avg20=None) is None

def test_compute_rvol_fractional():
    from rvol_computer import compute_rvol
    result = compute_rvol(today=150, avg20=100)
    assert abs(result - 1.5) < 1e-9

def test_compute_rvol_from_store():
    """OHLCVStore로부터 avg_volume을 조회하여 RVOL 계산."""
    from rvol_computer import compute_rvol_from_store
    from ohlcv_store import OHLCVStore
    s = OHLCVStore(":memory:")
    for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300)]:
        s.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
    # avg20=200, today=400 → 2.0
    result = compute_rvol_from_store("005930", today_volume=400, store=s, window=3)
    assert abs(result - 2.0) < 1e-9

if __name__ == "__main__":
    test_compute_rvol_basic()
    test_compute_rvol_zero_avg_returns_none()
    test_compute_rvol_none_avg_returns_none()
    test_compute_rvol_fractional()
    test_compute_rvol_from_store()
    print("[PASS] test_rvol_computer 전체 통과")
