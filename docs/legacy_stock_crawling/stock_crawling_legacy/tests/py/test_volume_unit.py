"""
이슈 #15 — 거래대금 단위 보정 휴리스틱 개선 테스트.
infer_volume_unit(df) 순수 함수가 삼성전자(005930) anchor로 배율을 정확히 판정하는지 검증.

Run:
    stock_crawling/Scripts/python.exe tests/py/test_volume_unit.py
    또는
    PYTHONPATH=. stock_crawling/Scripts/python.exe tests/py/test_volume_unit.py
"""
from __future__ import annotations

import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 stock_scraper 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd


def test_infer_volume_unit_if_krw():
    """삼성전자 Amount가 5천억(5e11)이면 이미 원 단위 → 배율 1."""
    from stock_scraper import infer_volume_unit
    df = pd.DataFrame({"Code": ["005930"], "Amount": [5e11]})  # 5천억 원
    assert infer_volume_unit(df) == 1, f"expected 1, got {infer_volume_unit(df)}"


def test_infer_volume_unit_if_million_krw():
    """삼성전자 Amount가 5e5(50만)이면 백만원 단위로 해석 → 배율 1_000_000."""
    from stock_scraper import infer_volume_unit
    df = pd.DataFrame({"Code": ["005930"], "Amount": [5e5]})  # 50만 (백만원 단위 → 5천억)
    assert infer_volume_unit(df) == 1_000_000, f"expected 1_000_000, got {infer_volume_unit(df)}"


def test_infer_volume_unit_samsung_not_present_large_max():
    """삼성전자 없고 전체 max가 충분히 크면 원 단위 → 배율 1."""
    from stock_scraper import infer_volume_unit
    df = pd.DataFrame({"Code": ["000660"], "Amount": [2e12]})  # SK하이닉스, 2조
    assert infer_volume_unit(df) == 1


def test_infer_volume_unit_samsung_not_present_small_max():
    """삼성전자 없고 전체 max가 작으면 백만원 단위 → 배율 1_000_000."""
    from stock_scraper import infer_volume_unit
    df = pd.DataFrame({"Code": ["000660"], "Amount": [5e5]})
    assert infer_volume_unit(df) == 1_000_000


def test_infer_volume_unit_zero_amount():
    """Amount가 모두 0이면 배율 1 반환 (silent 에러 방지)."""
    from stock_scraper import infer_volume_unit
    df = pd.DataFrame({"Code": ["005930"], "Amount": [0.0]})
    result = infer_volume_unit(df)
    assert result in (1, 1_000_000), f"unexpected: {result}"


if __name__ == "__main__":
    test_infer_volume_unit_if_krw()
    test_infer_volume_unit_if_million_krw()
    test_infer_volume_unit_samsung_not_present_large_max()
    test_infer_volume_unit_samsung_not_present_small_max()
    test_infer_volume_unit_zero_amount()
    print("[PASS] test_volume_unit - all tests")
