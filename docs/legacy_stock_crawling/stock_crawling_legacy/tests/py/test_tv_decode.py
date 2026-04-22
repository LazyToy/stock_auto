"""
TradingView 포지셔널 디코딩 sanity check 테스트.
Run: stock_crawling/Scripts/python.exe tests/py/test_tv_decode.py
"""
from __future__ import annotations
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []
def check(name: str, cond: bool, detail: str = "") -> None:
    results.append(bool(cond))
    print(f"{PASS if cond else FAIL} {name}" + (f" - {detail}" if detail else ""))


def test_decode_tv_row_ok():
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", 150.0, 2.5, 1e9, 151.0, 149.0, 2.5e12, "Technology"]
    row = decode_tv_row(d)
    check("decode_tv_row ok: ticker", row["ticker"] == "AAPL")
    check("decode_tv_row ok: name", row["name"] == "Apple Inc.")
    check("decode_tv_row ok: close", row["close"] == 150.0)
    check("decode_tv_row ok: change", row["change"] == 2.5)
    check("decode_tv_row ok: sector", row["sector"] == "Technology")

def test_decode_tv_row_bad_close_raises():
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", 0, 0, 0, 0, 0, 0, ""]
    try:
        decode_tv_row(d, strict=True)
        check("decode_tv_row strict bad_close raises", False, "should have raised ValueError")
    except ValueError:
        check("decode_tv_row strict bad_close raises", True)

def test_decode_tv_row_dot_ticker():
    """BRK.A, BRK.B 등 점(.) 포함 ticker 허용."""
    from us_stock_scraper import decode_tv_row
    d = ["BRK.A", "Berkshire Hathaway A", 600000.0, 0.5, 5e8, 601000.0, 599000.0, 8e11, "Financials"]
    row = decode_tv_row(d)
    check("decode_tv_row dot_ticker: sanity ok", row.get("_sanity_ok") is True, repr(row.get("_sanity_ok")))

def test_decode_tv_row_negative_close_nonstrict():
    """strict=False (기본) 에서는 bad close 라도 예외 없이 dict 반환, _sanity_ok=False."""
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", -1.0, 0, 0, 0, 0, 0, ""]
    row = decode_tv_row(d)
    check("decode_tv_row non-strict: no raise", True)
    check("decode_tv_row non-strict: _sanity_ok=False", row.get("_sanity_ok") is False, repr(row.get("_sanity_ok")))

def test_decode_tv_row_zero_volume_allowed():
    """volume=0 은 ETF/신규상장 허용 — sanity_ok=True."""
    from us_stock_scraper import decode_tv_row
    d = ["ETF", "Some ETF", 50.0, 0.0, 0, 50.5, 49.5, 1e9, "ETF"]
    row = decode_tv_row(d)
    check("decode_tv_row zero_volume: sanity_ok=True", row.get("_sanity_ok") is True, repr(row.get("_sanity_ok")))

def test_decode_tv_row_volume_field_d9():
    """d[9] 로 전달된 volume 이 'volume' 키로 반환된다."""
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", 150.0, 2.5, 1e9, 151.0, 149.0, 2.5e12, "Technology", 5_000_000.0]
    row = decode_tv_row(d)
    check("decode_tv_row d9_volume: volume field exists", "volume" in row)
    check("decode_tv_row d9_volume: volume=5_000_000", row.get("volume") == 5_000_000.0, repr(row.get("volume")))

def test_decode_tv_row_volume_missing_d9():
    """d[9] 없을 때 volume 은 0.0 으로 기본값."""
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", 150.0, 2.5, 1e9, 151.0, 149.0, 2.5e12, "Technology"]
    row = decode_tv_row(d)
    check("decode_tv_row no_d9: volume=0.0", row.get("volume") == 0.0, repr(row.get("volume")))


test_decode_tv_row_ok()
test_decode_tv_row_bad_close_raises()
test_decode_tv_row_dot_ticker()
test_decode_tv_row_negative_close_nonstrict()
test_decode_tv_row_zero_volume_allowed()
test_decode_tv_row_volume_field_d9()
test_decode_tv_row_volume_missing_d9()

passed = sum(results); total = len(results)
print(f"\n{'='*60}\n  RESULT: {passed}/{total} checks passed\n{'='*60}")
sys.exit(0 if passed == total else 1)
