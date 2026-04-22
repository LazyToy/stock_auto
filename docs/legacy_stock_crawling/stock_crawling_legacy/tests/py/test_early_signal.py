"""이슈 #7: 조기신호 판정 단위 테스트."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def test_early_signal_gated_by_rvol():
    from early_signal import is_early_signal
    assert is_early_signal(change=5, rvol=2.5, streak=3, close_ratio_52w=0.9) is False

def test_early_signal_hits_streak_branch():
    from early_signal import is_early_signal
    assert is_early_signal(change=5, rvol=3.0, streak=3, close_ratio_52w=0.5) is True

def test_early_signal_hits_52w_near_high_branch():
    from early_signal import is_early_signal
    assert is_early_signal(change=5, rvol=3.0, streak=1, close_ratio_52w=0.96) is True

def test_early_signal_out_of_range_upper():
    from early_signal import is_early_signal
    # 이미 +12% — 조기 아님 (range는 [+3%, +10%])
    assert is_early_signal(change=12, rvol=3.0, streak=5, close_ratio_52w=1.0) is False

def test_early_signal_out_of_range_lower():
    from early_signal import is_early_signal
    # +2.5% — change 미달
    assert is_early_signal(change=2.5, rvol=3.0, streak=3, close_ratio_52w=0.9) is False

def test_early_signal_neither_streak_nor_52w():
    from early_signal import is_early_signal
    # streak < 3이고 close_ratio_52w < 0.95 → False
    assert is_early_signal(change=5, rvol=3.5, streak=2, close_ratio_52w=0.90) is False

def test_build_early_signal_row():
    """시트 row 직렬화 검증."""
    from early_signal import build_early_signal_row
    row = build_early_signal_row(
        date="2026-04-17",
        ticker="005930",
        name="삼성전자",
        change=5.0,
        rvol=3.2,
        streak=3,
        close_ratio_52w=0.96,
        amount=500e8,
    )
    assert row[0] == "2026-04-17"
    assert row[1] == "005930"
    assert row[2] == "삼성전자"
    assert abs(row[3] - 5.0) < 0.01   # 등락률
    assert abs(row[4] - 3.2) < 0.01   # RVOL
    assert row[5] == 3                  # 연속봉
    assert abs(row[6] - 0.96) < 0.001 # 52주비율
    # 5일후수익률은 초기값 ""
    assert row[-1] == ""

if __name__ == "__main__":
    test_early_signal_gated_by_rvol()
    test_early_signal_hits_streak_branch()
    test_early_signal_hits_52w_near_high_branch()
    test_early_signal_out_of_range_upper()
    test_early_signal_out_of_range_lower()
    test_early_signal_neither_streak_nor_52w()
    test_build_early_signal_row()
    print("[PASS] test_early_signal 전체 통과")
