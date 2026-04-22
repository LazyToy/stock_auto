"""
Live smoke probe: hit real Naver WICS sector pages and print a summary.

Run
---
    PYTHONIOENCODING=utf-8 ./stock_crawling/Scripts/python.exe probe_sector_naver_live.py
"""
from __future__ import annotations

import sys
import traceback

from sector_map_kr import _fetch_naver

print("probing Naver WICS sector pages (live)...")
try:
    data = _fetch_naver()
except Exception:
    traceback.print_exc(limit=5)
    sys.exit(1)

print(f"\n[OK] tickers={len(data)}")
sectors = {}
for tkr, sec in data.items():
    sectors.setdefault(sec, []).append(tkr)
print(f"[OK] sectors={len(sectors)}")
print("\nsample sector sizes (first 15):")
for sec, tkrs in list(sectors.items())[:15]:
    print(f"  {sec:<30}  {len(tkrs):>4}")

print("\nsample tickers:")
for tkr, sec in list(data.items())[:10]:
    print(f"  {tkr} → {sec}")
