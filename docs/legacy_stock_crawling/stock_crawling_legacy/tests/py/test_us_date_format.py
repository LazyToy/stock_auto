"""
이슈 #10: US 스크래퍼 날짜 형식 단위 테스트 (옵션 C 하이브리드).
- make_sheet_month : 스프레드시트 파일명용 YYYYMM
- make_row_date    : 행 날짜·dedup key 용 YYYY-MM-DD
네트워크/파일 I/O 없음.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ──────────────────────────────────────────────
# make_sheet_month: 스프레드시트 파일명 (YYYYMM)
# ──────────────────────────────────────────────
def test_make_sheet_month_normal():
    from us_stock_scraper import make_sheet_month
    assert make_sheet_month(datetime(2026, 4, 17)) == "202604"


def test_make_sheet_month_january():
    """1월은 01 패딩."""
    from us_stock_scraper import make_sheet_month
    assert make_sheet_month(datetime(2026, 1, 3)) == "202601"


def test_make_sheet_month_december():
    from us_stock_scraper import make_sheet_month
    assert make_sheet_month(datetime(2026, 12, 31)) == "202612"


# ──────────────────────────────────────────────
# make_row_date: 행 날짜 (YYYY-MM-DD)
# ──────────────────────────────────────────────
def test_make_row_date_normal():
    from us_stock_scraper import make_row_date
    assert make_row_date(datetime(2026, 4, 17)) == "2026-04-17"


def test_make_row_date_single_digit_month_and_day():
    """월·일 한 자리 → 두 자리 패딩."""
    from us_stock_scraper import make_row_date
    assert make_row_date(datetime(2026, 1, 3)) == "2026-01-03"


def test_make_row_date_end_of_year():
    from us_stock_scraper import make_row_date
    assert make_row_date(datetime(2025, 12, 31)) == "2025-12-31"


# ──────────────────────────────────────────────
# 두 함수가 같은 datetime 에서 일관되게 분리되는지
# ──────────────────────────────────────────────
def test_sheet_month_and_row_date_consistent():
    """같은 날짜에서 파일명 월부분이 row_date 월부분과 일치."""
    from us_stock_scraper import make_sheet_month, make_row_date
    dt = datetime(2026, 4, 17)
    sheet = make_sheet_month(dt)   # "202604"
    row   = make_row_date(dt)      # "2026-04-17"
    # sheet 의 연월 == row_date 의 연월
    assert sheet == row[:4] + row[5:7], f"불일치: sheet={sheet}, row={row}"


if __name__ == "__main__":
    test_make_sheet_month_normal()
    test_make_sheet_month_january()
    test_make_sheet_month_december()
    test_make_row_date_normal()
    test_make_row_date_single_digit_month_and_day()
    test_make_row_date_end_of_year()
    test_sheet_month_and_row_date_consistent()
    print("[PASS] 전체 테스트 통과")
