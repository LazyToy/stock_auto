"""
TDD test: Naver WICS sector fetcher.

Hermetic — uses tiny HTML fixtures and an injected ``http_get`` callable,
so no live network. Exercises:

  * ``_parse_naver_sector_list`` — extract (no, name) from the group index.
  * ``_parse_naver_sector_detail`` — extract 6-digit tickers from a detail page.
  * ``_fetch_naver`` — end-to-end plumbing that walks the index, fetches each
    detail page, and builds the {ticker: sector_name} map.

Run
---
    ./stock_crawling/Scripts/python.exe test_sector_fetcher_naver.py
"""
from __future__ import annotations

import sys

from sector_map_kr import (
    _fetch_naver,
    _parse_naver_sector_detail,
    _parse_naver_sector_list,
)

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Fixtures — a minimal subset of real Naver markup (2026-04 snapshot)
# ---------------------------------------------------------------------------

SECTOR_LIST_HTML = """
<html><body>
<table class="type_1">
  <tr><th>업종명</th><th>전일대비</th></tr>
  <tr>
    <td><a href="/sise/sise_group_detail.naver?type=upjong&amp;no=306">전기장비</a></td>
    <td>+1.23%</td>
  </tr>
  <tr>
    <td><a href="/sise/sise_group_detail.naver?type=upjong&amp;no=308">인터넷과카탈로그소매</a></td>
    <td>-0.45%</td>
  </tr>
  <tr>
    <td><a href="/sise/sise_group_detail.naver?type=upjong&amp;no=294">통신장비</a></td>
    <td>+0.10%</td>
  </tr>
  <tr>
    <!-- noise row: no link -->
    <td>not a sector</td>
  </tr>
</table>
</body></html>
"""

DETAIL_306_HTML = """
<html><body>
<table>
  <tr>
    <td><a href="/item/main.naver?code=010120">LS ELECTRIC</a></td>
    <td>100,000</td>
  </tr>
  <tr>
    <td><a href="/item/main.naver?code=062040">산일전기</a></td>
    <td>50,000</td>
  </tr>
  <tr>
    <td><a href="/item/main.naver?code=010120">LS ELECTRIC</a></td>  <!-- dup -->
    <td>100,000</td>
  </tr>
</table>
</body></html>
"""

DETAIL_308_HTML = """
<html><body>
<a href="/item/main.naver?code=035420">NAVER</a>
<a href="/item/main.naver?code=035720">카카오</a>
</body></html>
"""

DETAIL_294_HTML = """
<html><body>
<a href="/item/main.naver?code=036810">에프에스티</a>
</body></html>
"""


# ---------------------------------------------------------------------------
# 1. _parse_naver_sector_list
# ---------------------------------------------------------------------------

sector_list = _parse_naver_sector_list(SECTOR_LIST_HTML)
check("sector list parsed to non-empty list", len(sector_list) == 3,
      f"got {len(sector_list)}")
check("sector list first entry is (306, '전기장비')",
      sector_list[0] == ("306", "전기장비"),
      f"got {sector_list[0]}")
check("sector list contains all three sectors",
      {s[0] for s in sector_list} == {"306", "308", "294"})
check("sector list names are decoded",
      all(nm and not nm.startswith("<") for _, nm in sector_list))


# ---------------------------------------------------------------------------
# 2. _parse_naver_sector_detail
# ---------------------------------------------------------------------------

tickers_306 = _parse_naver_sector_detail(DETAIL_306_HTML)
check("detail parser returns a list", isinstance(tickers_306, list))
check("detail parser dedupes identical tickers", len(tickers_306) == 2,
      f"got {tickers_306}")
check("detail parser preserves 6-digit ticker code",
      "010120" in tickers_306 and "062040" in tickers_306)

tickers_308 = _parse_naver_sector_detail(DETAIL_308_HTML)
check("detail parser handles plain anchors without table",
      set(tickers_308) == {"035420", "035720"})

empty_tickers = _parse_naver_sector_detail("<html></html>")
check("detail parser on empty HTML returns []", empty_tickers == [])


# ---------------------------------------------------------------------------
# 3. _fetch_naver end-to-end with fake http_get
# ---------------------------------------------------------------------------

class FakeHttp:
    INDEX_URL = "https://finance.naver.com/sise/sise_group.naver?type=upjong"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._pages = {
            self.INDEX_URL: SECTOR_LIST_HTML,
            "https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no=306": DETAIL_306_HTML,
            "https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no=308": DETAIL_308_HTML,
            "https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no=294": DETAIL_294_HTML,
        }

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        if url not in self._pages:
            raise RuntimeError(f"unexpected URL: {url}")
        return self._pages[url]


http = FakeHttp()
result = _fetch_naver(http_get=http, sleep=lambda s: None)

check("fetch_naver returns a dict", isinstance(result, dict))
check("fetch_naver mapped NAVER → 인터넷과카탈로그소매",
      result.get("035420") == "인터넷과카탈로그소매")
check("fetch_naver mapped LS ELECTRIC → 전기장비",
      result.get("010120") == "전기장비")
check("fetch_naver mapped 에프에스티 → 통신장비",
      result.get("036810") == "통신장비")
check("fetch_naver 6-digit keys", all(len(k) == 6 for k in result))
check("fetch_naver called index once", http.calls.count(FakeHttp.INDEX_URL) == 1)
check("fetch_naver called each detail page once",
      all(http.calls.count(u) == 1
          for u in http._pages if "detail" in u))
check("fetch_naver total ticker count",
      len(result) == 5, f"got {len(result)}")


# ---------------------------------------------------------------------------
# 4. _fetch_naver — if a detail page fails, others still populate
# ---------------------------------------------------------------------------

class FlakyHttp(FakeHttp):
    def __call__(self, url: str) -> str:
        self.calls.append(url)
        if "no=308" in url:
            raise RuntimeError("simulated network blip")
        return self._pages[url]


flaky = FlakyHttp()
partial = _fetch_naver(http_get=flaky, sleep=lambda s: None)
check("fetch_naver survives one failing detail page", len(partial) >= 3,
      f"got {len(partial)}")
check("fetch_naver still has sectors 306 + 294",
      partial.get("010120") == "전기장비"
      and partial.get("036810") == "통신장비")
check("fetch_naver missing the failed sector's tickers",
      "035420" not in partial and "035720" not in partial)


# ---------------------------------------------------------------------------
# 5. _fetch_naver — empty index raises
# ---------------------------------------------------------------------------

class EmptyHttp:
    def __call__(self, url: str) -> str:
        return "<html><body>no sectors</body></html>"


empty_raised = False
try:
    _fetch_naver(http_get=EmptyHttp(), sleep=lambda s: None)
except RuntimeError:
    empty_raised = True
check("fetch_naver raises RuntimeError when index is empty", empty_raised)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

passed = sum(1 for r in results if r)
total = len(results)
print()
print("=" * 60)
print(f"  RESULT: {passed}/{total} checks passed")
print("=" * 60)

sys.exit(0 if passed == total else 1)
