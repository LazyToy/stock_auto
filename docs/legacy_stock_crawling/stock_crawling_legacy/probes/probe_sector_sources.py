"""
Reconnaissance: which data source actually exposes KR sector/industry info?

Tries, in order:
  1. FinanceDataReader StockListing columns — does Dept or any other column
     already contain sector info?
  2. pykrx get_market_sector_classifications (if it exists)
  3. pykrx index listing with raw names (no keyword filter)
  4. KRX JSON endpoint with multiple candidate bld IDs

Prints what each returns so we can decide the real fetcher strategy.

Run
---
    ./stock_crawling/Scripts/python.exe probe_sector_sources.py
"""
from __future__ import annotations

import json
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime

TODAY = datetime.now().strftime("%Y%m%d")


def _section(title: str) -> None:
    print()
    print("#" * 70)
    print(f"# {title}")
    print("#" * 70)


# ---------------------------------------------------------------------------
# 1. FDR columns
# ---------------------------------------------------------------------------
_section("1. FinanceDataReader.StockListing('KRX') columns & sample")
try:
    import FinanceDataReader as fdr
    df = fdr.StockListing("KRX")
    print(f"rows: {len(df)}")
    print(f"columns: {list(df.columns)}")
    print("first row:")
    for col in df.columns:
        val = df.iloc[0][col]
        print(f"  {col!s:20s} = {val!r}")

    if "Dept" in df.columns:
        print("\n`Dept` value counts (top 20):")
        print(df["Dept"].value_counts().head(20).to_string())
except Exception:
    traceback.print_exc(limit=3)


# ---------------------------------------------------------------------------
# 2. pykrx direct sector classification (if exposed)
# ---------------------------------------------------------------------------
_section("2. pykrx module introspection")
try:
    from pykrx import stock
    attrs = [a for a in dir(stock) if "sector" in a.lower() or "industry" in a.lower()]
    print(f"sector/industry attrs: {attrs}")

    attrs2 = [a for a in dir(stock) if "classification" in a.lower()]
    print(f"classification attrs: {attrs2}")
except Exception:
    traceback.print_exc(limit=3)


# ---------------------------------------------------------------------------
# 3. pykrx index listing raw names
# ---------------------------------------------------------------------------
_section("3. pykrx get_index_ticker_list (KOSPI) raw names")
try:
    from pykrx import stock
    idxs = stock.get_index_ticker_list(TODAY, market="KOSPI")
    print(f"index count: {len(idxs)}")
    print("first 30 indices with names:")
    for i, idx in enumerate(idxs[:30]):
        try:
            name = stock.get_index_ticker_name(idx)
        except Exception as e:
            name = f"<ERR {e}>"
        print(f"  {idx} → {name}")
except Exception:
    traceback.print_exc(limit=3)


# ---------------------------------------------------------------------------
# 4. KRX JSON endpoint candidates
# ---------------------------------------------------------------------------
_section("4. KRX JSON candidate bld IDs")

KRX_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

candidates = [
    # Guessed candidates — from KRX Open-Data catalog conventions
    ("MDCSTAT03901", "STK", "sector index daily close (KOSPI)"),
    ("MDCSTAT03902", "STK", "member companies of sector index"),
    ("MDCSTAT04602", "STK", "business classification constituents"),
    ("MDCSTAT03501", "STK", "KOSPI200 sector constituents"),
    ("MDCSTAT02501", "STK", "stock basic info"),
    ("MDCSTAT01501", "STK", "stock listing by market"),
]

for bld, mkt, desc in candidates:
    print(f"\n--- bld={bld} mktId={mkt} ({desc}) ---")
    params = {
        "bld": f"dbms/MDC/STAT/standard/{bld}",
        "locale": "ko_KR",
        "mktId": mkt,
        "trdDd": TODAY,
        "money": "1",
        "csvxls_isNo": "false",
    }
    try:
        req = urllib.request.Request(
            KRX_URL,
            data=urllib.parse.urlencode(params).encode("utf-8"),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "http://data.krx.co.kr/",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            body = res.read().decode("utf-8")
            payload = json.loads(body)
            # show top-level keys and row count
            keys = list(payload.keys())
            print(f"  HTTP 200  keys={keys}")
            for k in keys:
                val = payload[k]
                if isinstance(val, list):
                    print(f"    {k}: list, len={len(val)}")
                    if val:
                        row_keys = list(val[0].keys()) if isinstance(val[0], dict) else []
                        print(f"       first row keys: {row_keys[:15]}")
    except Exception as e:
        print(f"  FAIL: {e}")


print()
print("=" * 70)
print("DONE")
print("=" * 70)
