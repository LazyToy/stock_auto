"""
Alternative KR sector sources:
  A) FDR alternative StockListing keys (KRX-INDEX, KRX-DESC, WICS, etc.)
  B) Naver Finance sector group pages (업종 분류)
"""
from __future__ import annotations

import re
import traceback

import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"

# -------- A) FDR alternate keys --------
print("=" * 60)
print("A) FDR StockListing alternate keys")
print("=" * 60)

for key in ["KRX-INDEX", "KRX-DESC", "KRX-DELISTING", "KRX-MARCAP",
            "KOSPI", "KOSDAQ", "KRX-STOCK", "KRX-SECTOR"]:
    print(f"\n--- fdr.StockListing({key!r}) ---")
    try:
        df = fdr.StockListing(key)
        print(f"  rows={len(df)}  cols={list(df.columns)}")
        if len(df) > 0:
            print("  first row:")
            print(df.head(1).to_string())
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")


# -------- B) Naver sector pages --------
print()
print("=" * 60)
print("B) Naver Finance sector group page")
print("=" * 60)

sess = requests.Session()
sess.headers.update({"User-Agent": UA})

try:
    r = sess.get(
        "https://finance.naver.com/sise/sise_group.naver?type=upjong",
        timeout=30,
    )
    r.encoding = "euc-kr"
    print(f"status={r.status_code}  bytes={len(r.text)}")

    soup = BeautifulSoup(r.text, "html.parser")
    sector_links = soup.select("table.type_1 tr a")
    print(f"sector link count: {len(sector_links)}")

    # Show first 10
    sectors = []
    for a in sector_links[:40]:
        href = a.get("href", "")
        m = re.search(r"no=(\d+)", href)
        if m:
            sectors.append((m.group(1), a.get_text(strip=True)))
    print(f"first {min(10,len(sectors))} sectors:")
    for no, name in sectors[:10]:
        print(f"  no={no}  name={name}")

    # Fetch detail page for the first sector
    if sectors:
        no, name = sectors[0]
        url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={no}"
        print(f"\nfetching detail for sector '{name}' (no={no})")
        r2 = sess.get(url, timeout=30)
        r2.encoding = "euc-kr"
        soup2 = BeautifulSoup(r2.text, "html.parser")
        # Stock links look like /item/main.naver?code=005930
        ticker_links = soup2.select("a[href*='/item/main.naver']")
        tickers = []
        for a in ticker_links:
            href = a.get("href", "")
            m = re.search(r"code=(\d{6})", href)
            if m:
                tkr = m.group(1)
                nm = a.get_text(strip=True)
                if nm:
                    tickers.append((tkr, nm))
        # dedupe
        seen = set()
        unique = []
        for tkr, nm in tickers:
            if tkr not in seen:
                seen.add(tkr)
                unique.append((tkr, nm))
        print(f"  ticker count: {len(unique)}")
        for tkr, nm in unique[:10]:
            print(f"  {tkr} {nm}")
except Exception:
    traceback.print_exc(limit=3)
