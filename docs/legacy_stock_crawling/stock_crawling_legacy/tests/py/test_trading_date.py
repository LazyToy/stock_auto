"""
이슈 #2 — 날짜 불일치 버그 수정 테스트.
resolve_trading_date(df, now) 순수 함수가 FDR Date 컬럼 기반으로 실제 거래일을 반환하는지 검증.

Run:
    stock_crawling/Scripts/python.exe tests/py/test_trading_date.py
    또는
    PYTHONPATH=. stock_crawling/Scripts/python.exe tests/py/test_trading_date.py
"""
from __future__ import annotations

import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 stock_scraper 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime

import pandas as pd


def test_resolve_trading_date_uses_fdr_date_column_when_present():
    """FDR 데이터에 Date 컬럼이 있고 모두 같은 날짜일 때 그 날짜를 사용."""
    from stock_scraper import resolve_trading_date
    df = pd.DataFrame({"Date": ["2026-04-17"] * 3})
    assert resolve_trading_date(df, now=datetime(2026, 4, 18)) == "20260417"


def test_resolve_trading_date_falls_back_to_now_when_no_date_column():
    """Date 컬럼 없으면 now 기준 날짜 반환."""
    from stock_scraper import resolve_trading_date
    df = pd.DataFrame({"Code": ["005930"]})  # Date 없음
    assert resolve_trading_date(df, now=datetime(2026, 4, 17)) == "20260417"


def test_resolve_trading_date_uses_most_common_when_mixed():
    """날짜가 혼재할 때 최빈 거래일 사용."""
    from stock_scraper import resolve_trading_date
    df = pd.DataFrame({"Date": ["2026-04-17", "2026-04-17", "2026-04-16"]})
    assert resolve_trading_date(df, now=datetime(2026, 4, 18)) == "20260417"


def test_resolve_trading_date_date_column_all_nan():
    """Date 컬럼이 있지만 전부 NaN이면 fallback to now."""
    from stock_scraper import resolve_trading_date
    df = pd.DataFrame({"Date": [None, None]})
    assert resolve_trading_date(df, now=datetime(2026, 4, 17)) == "20260417"


def test_resolve_trading_date_datetime64_column():
    """Date 컬럼이 datetime64 타입일 때도 동작해야 한다."""
    from stock_scraper import resolve_trading_date
    df = pd.DataFrame({"Date": pd.to_datetime(["2026-04-15", "2026-04-15"])})
    assert resolve_trading_date(df, now=datetime(2026, 4, 16)) == "20260415"


if __name__ == "__main__":
    test_resolve_trading_date_uses_fdr_date_column_when_present()
    test_resolve_trading_date_falls_back_to_now_when_no_date_column()
    test_resolve_trading_date_uses_most_common_when_mixed()
    test_resolve_trading_date_date_column_all_nan()
    test_resolve_trading_date_datetime64_column()
    print("[PASS] test_trading_date - all tests")
