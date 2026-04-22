"""
낙폭과대 필터 단위 테스트 (이슈 #6).

Run: stock_crawling/Scripts/python.exe tests/py/test_drop_stocks_filter.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append(bool(cond))
    print(f"{PASS if cond else FAIL} {name}" + (f" - {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# 1. 기본 필터 — threshold=-15
# ---------------------------------------------------------------------------

def test_filter_drop_stocks_basic():
    """등락률 <= -15% 인 종목만 반환해야 한다."""
    from stock_scraper import filter_drop_stocks
    df = pd.DataFrame(
        {"등락률": [-20.0, -10.0, 5.0], "거래대금": [100, 50, 200]},
        index=["A", "B", "C"],
    )
    result = filter_drop_stocks(df, threshold=-15)
    check("basic: 1건 반환", len(result) == 1, str(len(result)))
    check("basic: A 종목 포함", "A" in result.index)


# ---------------------------------------------------------------------------
# 2. 결과 없음
# ---------------------------------------------------------------------------

def test_filter_drop_stocks_empty():
    """조건 미충족 시 빈 DataFrame 반환."""
    from stock_scraper import filter_drop_stocks
    df = pd.DataFrame(
        {"등락률": [5.0, 10.0], "거래대금": [100, 200]},
        index=["A", "B"],
    )
    result = filter_drop_stocks(df, threshold=-15)
    check("empty: 0건 반환", len(result) == 0)


# ---------------------------------------------------------------------------
# 3. 기본 threshold=-15 (기본값)
# ---------------------------------------------------------------------------

def test_filter_drop_stocks_default_threshold():
    """기본값 threshold=-15 로 호출 시 -15% 초과 하락만 통과."""
    from stock_scraper import filter_drop_stocks
    df = pd.DataFrame(
        {"등락률": [-16.0, -14.0], "거래대금": [100, 200]},
        index=["A", "B"],
    )
    result = filter_drop_stocks(df)  # default threshold=-15
    check("default: 1건 (-16.0만 통과)", len(result) == 1, str(len(result)))


# ---------------------------------------------------------------------------
# 4. 경계 조건 — 정확히 -15.0 는 포함
# ---------------------------------------------------------------------------

def test_filter_drop_stocks_boundary():
    """-15.0 는 <= threshold 이므로 포함되어야 한다."""
    from stock_scraper import filter_drop_stocks
    df = pd.DataFrame(
        {"등락률": [-15.0, -14.9]},
        index=["A", "B"],
    )
    result = filter_drop_stocks(df, threshold=-15)
    check("boundary: -15.0 포함", len(result) == 1, str(len(result)))
    check("boundary: A 종목", "A" in result.index)


# ---------------------------------------------------------------------------
# 5. 복합 필터 — 거래대금 + 소폭 하락
# ---------------------------------------------------------------------------

def test_filter_drop_stocks_volume_and_drop():
    """거래대금 >= 500억 AND 등락률 <= -6% 조합 필터."""
    from stock_scraper import filter_drop_stocks_combined
    df = pd.DataFrame(
        {
            "등락률":  [-20.0,  -7.0,  -5.0,   5.0],
            "거래대금": [1e10,   6e10,  6e10,  1e10],
        },
        index=["A", "B", "C", "D"],
    )
    # A: -20% → 절대 기준 통과
    # B: -7%, 거래대금 600억 → 복합 기준 통과
    # C: -5%, 거래대금 600억 → -6% 미만이므로 탈락
    # D: +5% → 탈락
    result = filter_drop_stocks_combined(df)
    check("combined: A 포함 (-20%)", "A" in result.index)
    check("combined: B 포함 (-7%, 600억)", "B" in result.index)
    check("combined: C 제외 (-5%)", "C" not in result.index)
    check("combined: D 제외 (+5%)", "D" not in result.index)


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

test_filter_drop_stocks_basic()
test_filter_drop_stocks_empty()
test_filter_drop_stocks_default_threshold()
test_filter_drop_stocks_boundary()
test_filter_drop_stocks_volume_and_drop()

passed = sum(results)
total = len(results)
print()
print("=" * 60)
print(f"  RESULT: {passed}/{total} checks passed")
print("=" * 60)

sys.exit(0 if passed == total else 1)
