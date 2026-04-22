"""
Live end-to-end probe: SectorMapKR.load() → writes real cache → reads back.
"""
from __future__ import annotations

import json
import os
import sys

from sector_map_kr import SectorMapKR

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "sector_map_kr.json")
print(f"cache path: {CACHE}")

sm = SectorMapKR(cache_path=CACHE)
data = sm.load()
print(f"loaded {len(data)} tickers")

# Verify a handful of well-known ones
for tkr in ("005930", "000660", "035420", "035720", "207940", "051910"):
    sec = sm.lookup(tkr)
    print(f"  {tkr} → {sec}")

# Inspect cache file
with open(CACHE, "r", encoding="utf-8") as f:
    payload = json.load(f)
print(f"\ncache fetched_at={payload.get('fetched_at')}")
print(f"cache data entries={len(payload.get('data', {}))}")

# Second load should hit fresh cache (fetcher not called again)
sm2 = SectorMapKR(cache_path=CACHE)
data2 = sm2.load()
print(f"second load tickers={len(data2)} (should be same)")
sys.exit(0)
