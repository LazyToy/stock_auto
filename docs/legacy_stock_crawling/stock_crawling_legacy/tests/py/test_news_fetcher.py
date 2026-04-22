"""
TDD test: news_fetcher.

Hermetic — no live network calls. http_get and sleep are injected via
keyword arguments so every check is deterministic.

Run
---
    PYTHONIOENCODING=utf-8 ./stock_crawling/Scripts/python.exe test_news_fetcher.py
"""
from __future__ import annotations

import sys

from news_fetcher import fetch_kr_titles, fetch_us_titles

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

KR_HTML_PRIMARY = """
<html><body>
<div class="sub_section news_section">
  <ul>
    <li><a href="/news/1">삼성전자 신제품 발표</a></li>
    <li><a href="/news/2">  반도체 업황 회복 신호  </a></li>
    <li><a href="/news/3">외국인 순매수 지속</a></li>
    <li><a href="/news/4">코스피 2700 돌파</a></li>
    <li><a href="/news/5">5번째 뉴스</a></li>
  </ul>
</div>
</body></html>
"""

KR_HTML_FALLBACK = """
<html><body>
<div class="news_section">
  <a href="/news/A">낙수 효과 기대</a>
  <a href="/news/B">시장 반등</a>
</div>
</body></html>
"""

KR_HTML_NO_NEWS = """
<html><body>
<div class="other_section">
  <p>No news here</p>
</div>
</body></html>
"""

US_JSON_GOOD = '{"items":[{"title":"NVDA record earnings"},{"title":"NVDA guidance"},{"title":"AI boom continues"}]}'
US_JSON_GOOD_2 = '{"items":[{"title":"AAPL iPhone sales"},{"title":"AAPL services revenue"}]}'
US_JSON_MALFORMED = "not valid json {"
US_JSON_NO_ITEMS = '{"data": []}'
US_JSON_ITEMS_NOT_LIST = '{"items": "should be a list"}'


# ---------------------------------------------------------------------------
# KR 테스트 1: Happy path — 2 tickers × 3 titles = 6 titles
# ---------------------------------------------------------------------------

def make_kr_http(url_map: dict) -> object:
    def http_get(url: str) -> str:
        if url in url_map:
            return url_map[url]
        raise ValueError(f"unexpected URL: {url}")
    return http_get


kr_url_005930 = "https://finance.naver.com/item/main.naver?code=005930"
kr_url_000660 = "https://finance.naver.com/item/main.naver?code=000660"

sleep_calls: list[float] = []

def fake_sleep(t: float) -> None:
    sleep_calls.append(t)


titles_kr_happy = fetch_kr_titles(
    ["005930", "000660"],
    http_get=make_kr_http({
        kr_url_005930: KR_HTML_PRIMARY,
        kr_url_000660: KR_HTML_PRIMARY,
    }),
    sleep=fake_sleep,
    max_per_ticker=3,
)

check("KR happy path: returns a list", isinstance(titles_kr_happy, list))
check("KR happy path: 2 tickers × 3 titles = 6",
      len(titles_kr_happy) == 6,
      f"got {len(titles_kr_happy)}: {titles_kr_happy}")

# ---------------------------------------------------------------------------
# KR 테스트 2: titles이 strip됨
# ---------------------------------------------------------------------------

check("KR titles are stripped",
      all(t == t.strip() for t in titles_kr_happy),
      f"got {titles_kr_happy}")

# ---------------------------------------------------------------------------
# KR 테스트 3: max_per_ticker=2 → fixture 5개 중 2개만
# ---------------------------------------------------------------------------

titles_kr_max2 = fetch_kr_titles(
    ["005930"],
    http_get=make_kr_http({kr_url_005930: KR_HTML_PRIMARY}),
    sleep=fake_sleep,
    max_per_ticker=2,
)
check("KR max_per_ticker=2 → 2 titles from 5-item fixture",
      len(titles_kr_max2) == 2,
      f"got {len(titles_kr_max2)}: {titles_kr_max2}")

# ---------------------------------------------------------------------------
# KR 테스트 4: 한 ticker의 http_get이 예외를 던지면 다른 ticker 결과는 살아남음
# ---------------------------------------------------------------------------

def raises_on_second(url: str) -> str:
    if "005930" in url:
        return KR_HTML_PRIMARY
    raise ConnectionError("network error")


titles_kr_one_fail = fetch_kr_titles(
    ["005930", "000660"],
    http_get=raises_on_second,
    sleep=fake_sleep,
    max_per_ticker=3,
)
check("KR one ticker raises → other ticker's titles still returned, no crash",
      len(titles_kr_one_fail) == 3,
      f"got {len(titles_kr_one_fail)}: {titles_kr_one_fail}")

# ---------------------------------------------------------------------------
# KR 테스트 5: 뉴스 섹션 없는 HTML → 빈 문자열 없이 빈 리스트
# ---------------------------------------------------------------------------

titles_kr_no_news = fetch_kr_titles(
    ["005930"],
    http_get=make_kr_http({kr_url_005930: KR_HTML_NO_NEWS}),
    sleep=fake_sleep,
    max_per_ticker=3,
)
check("KR no news section → returns [] (no crash, no empty strings)",
      titles_kr_no_news == [],
      f"got {titles_kr_no_news}")

# ---------------------------------------------------------------------------
# KR 테스트 6: 빈 tickers 리스트 → []
# ---------------------------------------------------------------------------

titles_kr_empty = fetch_kr_titles(
    [],
    http_get=make_kr_http({}),
    sleep=fake_sleep,
)
check("KR empty tickers → []", titles_kr_empty == [])

# ---------------------------------------------------------------------------
# KR 테스트 7: sleep이 tickers 사이에 호출됨
# ---------------------------------------------------------------------------

sleep_calls_kr: list[float] = []

def counting_sleep(t: float) -> None:
    sleep_calls_kr.append(t)


fetch_kr_titles(
    ["005930", "000660", "373220"],
    http_get=make_kr_http({
        "https://finance.naver.com/item/main.naver?code=005930": KR_HTML_PRIMARY,
        "https://finance.naver.com/item/main.naver?code=000660": KR_HTML_PRIMARY,
        "https://finance.naver.com/item/main.naver?code=373220": KR_HTML_PRIMARY,
    }),
    sleep=counting_sleep,
    max_per_ticker=1,
)
# 3 tickers → sleep called at least once (between requests)
check("KR sleep called between tickers (3 tickers → at least 1 sleep call)",
      len(sleep_calls_kr) >= 1,
      f"sleep called {len(sleep_calls_kr)} times")

# ---------------------------------------------------------------------------
# KR 테스트 8: 티커 zero-padding — "5930" → URL에 "005930"이 포함
# ---------------------------------------------------------------------------

seen_urls_kr: list[str] = []

def capturing_http(url: str) -> str:
    seen_urls_kr.append(url)
    return KR_HTML_PRIMARY


fetch_kr_titles(
    ["5930"],
    http_get=capturing_http,
    sleep=fake_sleep,
    max_per_ticker=1,
)
check("KR ticker '5930' is zero-padded to '005930' in URL",
      any("005930" in u for u in seen_urls_kr),
      f"seen URLs: {seen_urls_kr}")

# ---------------------------------------------------------------------------
# KR 테스트 9: fallback selector (.news_section a) 동작 확인
# ---------------------------------------------------------------------------

kr_url_fallback_ticker = "https://finance.naver.com/item/main.naver?code=000270"

titles_kr_fallback = fetch_kr_titles(
    ["000270"],
    http_get=make_kr_http({kr_url_fallback_ticker: KR_HTML_FALLBACK}),
    sleep=fake_sleep,
    max_per_ticker=3,
)
check("KR fallback selector (.news_section a) returns titles",
      len(titles_kr_fallback) >= 1,
      f"got {titles_kr_fallback}")
check("KR fallback selector titles are non-empty strings",
      all(isinstance(t, str) and t for t in titles_kr_fallback))

# ---------------------------------------------------------------------------
# US 테스트 1: Happy path — 2 tickers × items
# ---------------------------------------------------------------------------

us_url_nvda = "https://api.stock.naver.com/news/stock/NVDA?pageSize=3&page=1"
us_url_aapl = "https://api.stock.naver.com/news/stock/AAPL?pageSize=3&page=1"

sleep_calls_us: list[float] = []

def us_fake_sleep(t: float) -> None:
    sleep_calls_us.append(t)


titles_us_happy = fetch_us_titles(
    ["NVDA", "AAPL"],
    http_get=make_kr_http({
        us_url_nvda: US_JSON_GOOD,
        us_url_aapl: US_JSON_GOOD_2,
    }),
    sleep=us_fake_sleep,
    max_per_ticker=3,
)
check("US happy path: returns a list", isinstance(titles_us_happy, list))
check("US happy path: NVDA 3 + AAPL 2 = 5 titles",
      len(titles_us_happy) == 5,
      f"got {len(titles_us_happy)}: {titles_us_happy}")
check("US happy path: contains NVDA title",
      "NVDA record earnings" in titles_us_happy)

# ---------------------------------------------------------------------------
# US 테스트 2: 한 ticker JSON이 malformed → skip, 다른 ticker 성공
# ---------------------------------------------------------------------------

us_url_bad = "https://api.stock.naver.com/news/stock/BAD?pageSize=3&page=1"

titles_us_bad_json = fetch_us_titles(
    ["BAD", "NVDA"],
    http_get=make_kr_http({
        us_url_bad: US_JSON_MALFORMED,
        us_url_nvda: US_JSON_GOOD,
    }),
    sleep=us_fake_sleep,
    max_per_ticker=3,
)
check("US malformed JSON on one ticker → other ticker still works",
      len(titles_us_bad_json) == 3,
      f"got {len(titles_us_bad_json)}: {titles_us_bad_json}")

# ---------------------------------------------------------------------------
# US 테스트 3: 'items' 키 없음 → skip
# ---------------------------------------------------------------------------

us_url_no_items = "https://api.stock.naver.com/news/stock/NOKEY?pageSize=3&page=1"

titles_us_no_key = fetch_us_titles(
    ["NOKEY"],
    http_get=make_kr_http({us_url_no_items: US_JSON_NO_ITEMS}),
    sleep=us_fake_sleep,
    max_per_ticker=3,
)
check("US missing 'items' key → [] (no crash)",
      titles_us_no_key == [],
      f"got {titles_us_no_key}")

# ---------------------------------------------------------------------------
# US 테스트 4: 'items'가 list가 아님 → skip
# ---------------------------------------------------------------------------

us_url_not_list = "https://api.stock.naver.com/news/stock/NOTLIST?pageSize=3&page=1"

titles_us_not_list = fetch_us_titles(
    ["NOTLIST"],
    http_get=make_kr_http({us_url_not_list: US_JSON_ITEMS_NOT_LIST}),
    sleep=us_fake_sleep,
    max_per_ticker=3,
)
check("US 'items' not a list → [] (no crash)",
      titles_us_not_list == [],
      f"got {titles_us_not_list}")

# ---------------------------------------------------------------------------
# US 테스트 5: max_per_ticker cap
# ---------------------------------------------------------------------------

titles_us_max1 = fetch_us_titles(
    ["NVDA"],
    http_get=make_kr_http({us_url_nvda: US_JSON_GOOD}),
    sleep=us_fake_sleep,
    max_per_ticker=1,
)
check("US max_per_ticker=1 → 1 title from 3-item fixture",
      len(titles_us_max1) == 1,
      f"got {len(titles_us_max1)}: {titles_us_max1}")

# ---------------------------------------------------------------------------
# US 테스트 6: 빈 tickers → []
# ---------------------------------------------------------------------------

titles_us_empty = fetch_us_titles(
    [],
    http_get=make_kr_http({}),
    sleep=us_fake_sleep,
)
check("US empty tickers → []", titles_us_empty == [])

# ---------------------------------------------------------------------------
# US 테스트 7: 한 ticker http_get이 예외 → 다른 ticker 성공
# ---------------------------------------------------------------------------

def us_raises_on_nvda(url: str) -> str:
    if "NVDA" in url:
        raise ConnectionError("timeout")
    return US_JSON_GOOD_2


titles_us_one_fail = fetch_us_titles(
    ["NVDA", "AAPL"],
    http_get=us_raises_on_nvda,
    sleep=us_fake_sleep,
    max_per_ticker=3,
)
check("US one ticker raises → other ticker's titles still returned",
      len(titles_us_one_fail) == 2,
      f"got {len(titles_us_one_fail)}: {titles_us_one_fail}")

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
