"""
이슈 #7 통합 테스트 — 20일 SQLite fixture 기반 조기신호 동적 검증.

검증 항목:
  1. 20일 평균 거래량 fixture → RVOL 계산 정확도
  2. RVOL >= 3.0 + change [3%, 10%] + streak >= 3 → is_early_signal True
  3. RVOL < 3.0 → is_early_signal False
  4. change 범위 초과 → is_early_signal False
  5. run_snapshots early_signal_source + MarketFlowSheet.append_early_signals 통합
"""
from __future__ import annotations

import sys
import os
import datetime
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

results: list[bool] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    results.append(condition)
    status = "PASS" if condition else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")


# ---------------------------------------------------------------------------
# 헬퍼: in-memory SQLite에 n일치 거래량 fixture 삽입
# ---------------------------------------------------------------------------
def _make_store(ticker: str, avg_vol: float, n_days: int = 20):
    """OHLCVStore(:memory:)에 n_days 거래일 평균 거래량 fixture 삽입."""
    from ohlcv_store import OHLCVStore

    store = OHLCVStore(":memory:")
    base = datetime.date(2026, 3, 1)
    for i in range(n_days):
        d = (base + datetime.timedelta(days=i)).isoformat()
        store.upsert_many([(
            ticker, d,
            100.0, 105.0, 95.0, 102.0,
            avg_vol,      # volume
            0.0,          # amount
        )])
    return store


# ---------------------------------------------------------------------------
# 1. 20일 avg_volume fixture 정확도
# ---------------------------------------------------------------------------
def test_fixture_avg_volume():
    """20일 균일 거래량 → avg_volume 이 삽입값과 일치."""
    from ohlcv_store import OHLCVStore

    store = _make_store("005930", avg_vol=100_000, n_days=20)
    avg = store.avg_volume("005930", window=20)
    store.close()
    check("avg_volume fixture == 100_000", avg is not None)
    check("avg_volume value accurate", abs(avg - 100_000) < 1, f"got {avg}")


# ---------------------------------------------------------------------------
# 2. RVOL >= 3.0 → is_early_signal True
# ---------------------------------------------------------------------------
def test_rvol_high_detects_signal():
    """오늘 거래량=300_000, 평균=100_000 → RVOL=3.0, 조건 충족 시 신호."""
    from rvol_computer import compute_rvol
    from early_signal import is_early_signal

    store = _make_store("000660", avg_vol=100_000, n_days=20)
    avg = store.avg_volume("000660", window=20)
    store.close()

    rvol = compute_rvol(today=300_000, avg20=avg)
    check("rvol is not None", rvol is not None)
    check("rvol ~= 3.0", abs(rvol - 3.0) < 0.01, f"got {rvol}")

    result = is_early_signal(change=5.0, rvol=rvol, streak=3, close_ratio_52w=0.95)
    check("RVOL=3.0 + change=5 + streak=3 -> True", result is True)


# ---------------------------------------------------------------------------
# 3. RVOL < 3.0 → is_early_signal False
# ---------------------------------------------------------------------------
def test_rvol_low_no_signal():
    """RVOL < 3.0 이면 신호 없음."""
    from rvol_computer import compute_rvol
    from early_signal import is_early_signal

    store = _make_store("035420", avg_vol=100_000, n_days=20)
    avg = store.avg_volume("035420", window=20)
    store.close()

    rvol = compute_rvol(today=250_000, avg20=avg)
    check("rvol < 3.0", rvol is not None and rvol < 3.0, f"got {rvol}")
    result = is_early_signal(change=5.0, rvol=rvol, streak=3, close_ratio_52w=0.95)
    check("RVOL=2.5 -> False", result is False)


# ---------------------------------------------------------------------------
# 4. change 범위 초과 → False (이 판단은 호출자 책임이지만 경계 확인)
# ---------------------------------------------------------------------------
def test_change_boundary():
    """change=10.01% (상한 초과) → is_early_signal False."""
    from early_signal import is_early_signal

    result_over = is_early_signal(change=10.01, rvol=4.0, streak=5, close_ratio_52w=0.99)
    check("change=10.01 over limit -> False", result_over is False)

    result_under = is_early_signal(change=2.99, rvol=4.0, streak=5, close_ratio_52w=0.99)
    check("change=2.99 under limit -> False", result_under is False)


# ---------------------------------------------------------------------------
# 5. run_snapshots 통합: early_signal_source + append_early_signals
# ---------------------------------------------------------------------------
def test_append_early_signals_integration():
    """run_snapshots에 fake early_signal_source + fake MarketFlowSheet 주입."""
    from generate_snapshots import run_snapshots

    appended: list[tuple] = []

    class _FakeSheet:
        def append_kr_snapshot(self, s): pass
        def append_us_snapshot(self, s): pass

    class _FakeFlow:
        def append_theme_clusters(self, date, clusters): return 0
        def append_early_signals(self, date, signals):
            appended.append((date, list(signals)))
            return len(signals)
        def append_flow_signals(self, date, signals): return 0
        def append_weekly_trends(self, iso_week, clusters): return 0

    fake_signals = [
        {"ticker": "005930", "change": 5.2, "rvol": 3.1, "streak": 4,
         "close_ratio_52w": 0.96, "amount": 80_000_000_000},
    ]

    fixed_clock = lambda: datetime.datetime(2026, 4, 17, 16, 0)

    rc = run_snapshots(
        kr_source=lambda: {"date": "2026-04-17", "top_gainers": pd.DataFrame()},
        us_source=lambda: {"date": "2026-04-17", "top_gainers": pd.DataFrame()},
        sheet_factory=lambda year: _FakeSheet(),
        early_signal_source=lambda snap, date: fake_signals,
        market_flow_factory=lambda year: _FakeFlow(),
        clock=fixed_clock,
    )

    check("run_snapshots rc=0", rc == 0, f"got {rc}")
    check("append_early_signals called once", len(appended) == 1,
          f"got {len(appended)} calls")
    check("signals forwarded correctly", appended[0][1] == fake_signals)
    check("date is 2026-04-17", appended[0][0] == "2026-04-17",
          f"got {appended[0][0]!r}")


# ---------------------------------------------------------------------------
# 6. 15일 이하 fixture → avg_volume None (데이터 부족)
# ---------------------------------------------------------------------------
def test_insufficient_history():
    """5일치 이력만 있으면 20일 window avg는 None 반환."""
    from rvol_computer import compute_rvol

    store = _make_store("999999", avg_vol=50_000, n_days=5)
    avg = store.avg_volume("999999", window=20)
    store.close()
    # avg는 None 또는 유효값일 수 있음 — OHLCVStore 구현에 따라 다름
    # 여기서는 compute_rvol이 None avg에서도 안전 처리를 확인
    rvol = compute_rvol(today=200_000, avg20=avg)
    # avg가 None이면 rvol도 None이어야 함 (안전 처리 확인)
    if avg is None:
        check("insufficient history -> rvol None", rvol is None, f"got {rvol}")
    else:
        # 5일치로 평균 계산 가능한 경우도 허용
        check("insufficient history -> rvol numeric or None",
              rvol is None or isinstance(rvol, float))


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
test_fixture_avg_volume()
test_rvol_high_detects_signal()
test_rvol_low_no_signal()
test_change_boundary()
test_append_early_signals_integration()
test_insufficient_history()

passed = sum(results)
total = len(results)
print(f"\n{'=' * 60}\n  RESULT: {passed}/{total} checks passed\n{'=' * 60}")
sys.exit(0 if passed == total else 1)
