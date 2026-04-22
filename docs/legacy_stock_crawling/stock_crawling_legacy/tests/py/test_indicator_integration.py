"""
이슈 #1 — streak_indicators 통합 테스트.
build_indicator_columns(indicators, prev_close, today_open) 순수 함수가
5개 컬럼 값을 올바르게 생성하는지 검증.

Run:
    stock_crawling/Scripts/python.exe tests/py/test_indicator_integration.py
    또는
    PYTHONPATH=. stock_crawling/Scripts/python.exe tests/py/test_indicator_integration.py
"""
from __future__ import annotations

import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 stock_scraper 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def test_build_indicator_columns_all_fields_present():
    """compute_indicators 결과 + prev_close/today_open 으로 5개 컬럼 값이 나와야 한다."""
    from stock_scraper import build_indicator_columns
    indicators = {
        "is_52w_high": True, "is_52w_low": False,
        "streak_days": 5, "atr14": 1200.0, "atr14_pct": 3.24,
    }
    cols = build_indicator_columns(indicators, prev_close=10000.0, today_open=10500.0)
    assert cols == ["신고", "", 5, 3.24, 5.0], f"got {cols}"


def test_build_indicator_columns_empty_52w():
    """52주 신고/신저 모두 False, 하락 연속봉, 음수 갭."""
    from stock_scraper import build_indicator_columns
    indicators = {
        "is_52w_high": False, "is_52w_low": False,
        "streak_days": -2, "atr14": 0.0, "atr14_pct": 0.0,
    }
    cols = build_indicator_columns(indicators, prev_close=10000.0, today_open=9500.0)
    assert cols == ["", "", -2, 0.0, -5.0], f"got {cols}"


def test_build_indicator_columns_gap_zero_prev():
    """prev_close == 0 방어 케이스 — 갭은 0.0으로."""
    from stock_scraper import build_indicator_columns
    indicators = {
        "is_52w_high": False, "is_52w_low": True,
        "streak_days": 0, "atr14": 100.0, "atr14_pct": 1.11,
    }
    cols = build_indicator_columns(indicators, prev_close=0.0, today_open=100.0)
    assert cols[4] == 0.0, f"갭 should be 0.0 when prev_close==0, got {cols[4]}"


def test_build_indicator_columns_52w_low():
    """52주 신저 True 케이스."""
    from stock_scraper import build_indicator_columns
    indicators = {
        "is_52w_high": False, "is_52w_low": True,
        "streak_days": -3, "atr14": 500.0, "atr14_pct": 2.5,
    }
    cols = build_indicator_columns(indicators, prev_close=20000.0, today_open=19000.0)
    assert cols[0] == "", f"52주신고 should be empty"
    assert cols[1] == "신저", f"52주신저 should be '신저'"
    assert cols[2] == -3, f"연속봉 should be -3"
    assert cols[3] == 2.5, f"ATR14(%) should be 2.5"
    assert cols[4] == round((19000 - 20000) / 20000 * 100, 2), f"갭(%) mismatch"


def test_build_indicator_columns_returns_list_of_5():
    """반환값이 정확히 5개 항목인지 확인."""
    from stock_scraper import build_indicator_columns
    indicators = {
        "is_52w_high": False, "is_52w_low": False,
        "streak_days": 1, "atr14": 100.0, "atr14_pct": 1.0,
    }
    cols = build_indicator_columns(indicators, prev_close=10000.0, today_open=10100.0)
    assert len(cols) == 5, f"expected 5 columns, got {len(cols)}"


if __name__ == "__main__":
    test_build_indicator_columns_all_fields_present()
    test_build_indicator_columns_empty_52w()
    test_build_indicator_columns_gap_zero_prev()
    test_build_indicator_columns_52w_low()
    test_build_indicator_columns_returns_list_of_5()
    print("[PASS] test_indicator_integration - all tests")
