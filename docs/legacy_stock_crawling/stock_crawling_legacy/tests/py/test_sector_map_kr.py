"""
TDD test: sector_map_kr.SectorMapKR — cache-aware KR sector loader.

Covers cache lifecycle (missing / fresh / stale / corrupt), coverage-triggered
refresh, fetcher-failure fallback, and lookup/classify behavior. The network
fetcher is injected as a fake, so this unit test is hermetic — no pykrx, no
KRX API calls.

Run
---
    ./stock_crawling/Scripts/python.exe test_sector_map_kr.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

from sector_map_kr import (
    CACHE_MAX_AGE_DAYS,
    MIN_COVERAGE,
    SectorMapKR,
    UNKNOWN_SECTOR,
)

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


class FakeFetcher:
    def __init__(self, data: dict[str, str], fail: bool = False) -> None:
        self._data = dict(data)
        self._fail = fail
        self.calls = 0

    def __call__(self) -> dict[str, str]:
        self.calls += 1
        if self._fail:
            raise RuntimeError("fetcher failed")
        return dict(self._data)


def frozen(when: datetime):
    return lambda: when


def write_cache(path: str, fetched_at: str, data: dict[str, str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": fetched_at, "data": data}, f, ensure_ascii=False)


TMP = tempfile.mkdtemp(prefix="sectormap_test_")
NOW = datetime(2026, 4, 13)


# ---------------------------------------------------------------------------
# 1. Cache missing → fetcher called, cache written
# ---------------------------------------------------------------------------

path1 = os.path.join(TMP, "miss.json")
f1 = FakeFetcher({"005930": "반도체", "000660": "반도체"})
sm1 = SectorMapKR(cache_path=path1, fetcher=f1, clock=frozen(NOW))
m1 = sm1.load()
check("missing cache → fetcher called once", f1.calls == 1)
check("missing cache → returned data contains Samsung sector",
      m1.get("005930") == "반도체")
check("missing cache → cache file is created on disk",
      os.path.exists(path1))

# ---------------------------------------------------------------------------
# 2. Fresh cache (≤30d) → fetcher NOT called
# ---------------------------------------------------------------------------

path2 = os.path.join(TMP, "fresh.json")
write_cache(path2, "2026-04-01", {"005930": "CACHED"})  # 12 days old
f2 = FakeFetcher({"005930": "FRESH"})
sm2 = SectorMapKR(cache_path=path2, fetcher=f2, clock=frozen(NOW))
m2 = sm2.load()
check("fresh cache → fetcher not called", f2.calls == 0)
check("fresh cache → data served from cache", m2.get("005930") == "CACHED")

# ---------------------------------------------------------------------------
# 3. Stale cache (>30d) → fetcher called
# ---------------------------------------------------------------------------

path3 = os.path.join(TMP, "stale.json")
write_cache(path3, "2026-02-01", {"005930": "OLD"})  # 71 days old
f3 = FakeFetcher({"005930": "NEW"})
sm3 = SectorMapKR(cache_path=path3, fetcher=f3, clock=frozen(NOW))
m3 = sm3.load()
check("stale cache → fetcher called", f3.calls == 1)
check("stale cache → data replaced by fresh fetch", m3.get("005930") == "NEW")

# ---------------------------------------------------------------------------
# 4. Fetcher fails but cache exists → fallback to cache (even if stale)
# ---------------------------------------------------------------------------

path4 = os.path.join(TMP, "fallback.json")
write_cache(path4, "2026-02-01", {"005930": "OLD_BUT_USABLE"})
f4 = FakeFetcher({}, fail=True)
sm4 = SectorMapKR(cache_path=path4, fetcher=f4, clock=frozen(NOW))
m4 = sm4.load()
check("fetch fails + cache exists → fetcher attempted once", f4.calls == 1)
check("fetch fails + cache exists → returned stale cache",
      m4.get("005930") == "OLD_BUT_USABLE")

# ---------------------------------------------------------------------------
# 5. Fetcher fails + no cache → raises
# ---------------------------------------------------------------------------

path5 = os.path.join(TMP, "nocache.json")
f5 = FakeFetcher({}, fail=True)
sm5 = SectorMapKR(cache_path=path5, fetcher=f5, clock=frozen(NOW))
raised_runtime = False
try:
    sm5.load()
except RuntimeError:
    raised_runtime = True
check("fetch fails + no cache → raises RuntimeError", raised_runtime)

# ---------------------------------------------------------------------------
# 6. Coverage below threshold → refresh triggered even on a fresh cache
# ---------------------------------------------------------------------------

path6 = os.path.join(TMP, "lowcov.json")
write_cache(path6, "2026-04-10", {"005930": "A"})  # fresh but only 1 entry
f6 = FakeFetcher({
    "005930": "A", "000660": "B", "035720": "C", "035420": "D",
    "207940": "E", "051910": "F", "006400": "G", "005380": "H",
})
known = {"005930", "000660", "035720", "035420",
         "207940", "051910", "006400", "005380"}
sm6 = SectorMapKR(cache_path=path6, fetcher=f6, clock=frozen(NOW))
sm6.load(known_tickers=known)
check("coverage < 95% triggers refresh", f6.calls == 1)

# ---------------------------------------------------------------------------
# 7. Coverage ≥ threshold on a fresh cache → no refresh
# ---------------------------------------------------------------------------

path7 = os.path.join(TMP, "fullcov.json")
full_data = {
    "005930": "A", "000660": "B", "035720": "C", "035420": "D",
    "207940": "E", "051910": "F", "006400": "G", "005380": "H",
}
write_cache(path7, "2026-04-10", full_data)
f7 = FakeFetcher({"005930": "SHOULD_NOT_APPEAR"})
sm7 = SectorMapKR(cache_path=path7, fetcher=f7, clock=frozen(NOW))
sm7.load(known_tickers=set(full_data.keys()))
check("coverage ≥ 95% keeps using cache", f7.calls == 0)

# ---------------------------------------------------------------------------
# 8. Corrupt cache → treated as missing
# ---------------------------------------------------------------------------

path8 = os.path.join(TMP, "corrupt.json")
with open(path8, "w", encoding="utf-8") as fh:
    fh.write("not json{{{")
f8 = FakeFetcher({"005930": "OK"})
sm8 = SectorMapKR(cache_path=path8, fetcher=f8, clock=frozen(NOW))
m8 = sm8.load()
check("corrupt cache → fetcher called", f8.calls == 1)
check("corrupt cache → data from fresh fetch", m8.get("005930") == "OK")

# ---------------------------------------------------------------------------
# 9. lookup() — known + unknown
# ---------------------------------------------------------------------------

f9 = FakeFetcher({"005930": "반도체"})
sm9 = SectorMapKR(cache_path=os.path.join(TMP, "lookup.json"),
                  fetcher=f9, clock=frozen(NOW))
check("lookup known ticker returns its sector",
      sm9.lookup("005930") == "반도체")
check("lookup unknown ticker returns UNKNOWN_SECTOR",
      sm9.lookup("999999") == UNKNOWN_SECTOR)

# ---------------------------------------------------------------------------
# 10. classify()
# ---------------------------------------------------------------------------

f10 = FakeFetcher({"005930": "반도체", "000660": "반도체"})
sm10 = SectorMapKR(cache_path=os.path.join(TMP, "classify.json"),
                   fetcher=f10, clock=frozen(NOW))
classified = sm10.classify(["005930", "999999"])
check("classify maps known ticker", classified.get("005930") == "반도체")
check("classify assigns UNKNOWN_SECTOR to unknown",
      classified.get("999999") == UNKNOWN_SECTOR)

# ---------------------------------------------------------------------------
# 11. Zero-padding: lookup a 5-digit string should still hit 005930
# ---------------------------------------------------------------------------

f11 = FakeFetcher({"005930": "반도체"})
sm11 = SectorMapKR(cache_path=os.path.join(TMP, "pad.json"),
                   fetcher=f11, clock=frozen(NOW))
check("lookup zero-pads 5-digit ticker to 6 digits",
      sm11.lookup("5930") == "반도체")

# ---------------------------------------------------------------------------
# 12. Constants
# ---------------------------------------------------------------------------

check("CACHE_MAX_AGE_DAYS == 30", CACHE_MAX_AGE_DAYS == 30)
check("MIN_COVERAGE == 0.95", MIN_COVERAGE == 0.95)
check("UNKNOWN_SECTOR == '기타'", UNKNOWN_SECTOR == "기타")

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

passed = sum(1 for r in results if r)
total = len(results)
print()
print("=" * 60)
print(f"  RESULT: {passed}/{total} checks passed")
print("=" * 60)

shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if passed == total else 1)
