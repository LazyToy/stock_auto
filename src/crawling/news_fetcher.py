"""
news_fetcher — hermetic KR+US news-title fetcher.

Both functions accept injectable ``http_get`` and ``sleep`` callables so
the test suite can run without any network access.  Per-ticker failures are
logged to stderr and skipped; the aggregate never raises.
"""
from __future__ import annotations

import json
import sys
import time as _time
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# Chrome-style UA shared by both fetchers
# ---------------------------------------------------------------------------
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Optional BeautifulSoup import (mirrors sector_map_kr.py pattern)
# ---------------------------------------------------------------------------
_BeautifulSoup = None
try:
    from bs4 import BeautifulSoup as _BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# Default HTTP helpers
# ---------------------------------------------------------------------------

def _default_kr_http_get(url: str) -> str:
    """Production KR GET: EUC-KR decode with UTF-8 fallback (mirrors sector_map_kr._default_http_get)."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = res.read()
    try:
        return raw.decode("euc-kr")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _default_us_http_get(url: str) -> str:
    """Production US GET: UTF-8 JSON."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8")


# ---------------------------------------------------------------------------
# KR HTML parsing helpers
# ---------------------------------------------------------------------------

def _parse_kr_titles(html: str, max_per_ticker: int) -> list[str]:
    """Extract news titles from a Naver finance item page."""
    if _BS4_AVAILABLE and _BeautifulSoup is not None:
        soup = _BeautifulSoup(html, "html.parser")
        articles = soup.select(".sub_section.news_section ul li a")
        if not articles:
            articles = soup.select(".news_section a")
        titles = []
        for a in articles[:max_per_ticker]:
            title = a.get_text(strip=True)
            if title:
                titles.append(title)
        return titles
    else:
        # Regex fallback when bs4 is not installed
        import re
        titles: list[str] = []
        # Try to narrow to news_section block first
        block_match = re.search(
            r'class=["\'][^"\']*news_section[^"\']*["\'].*?</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        search_area = block_match.group(0) if block_match else html
        for m in re.finditer(r'<a\b[^>]*>(.*?)</a>', search_area, re.DOTALL | re.IGNORECASE):
            raw = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if raw:
                titles.append(raw)
            if len(titles) >= max_per_ticker:
                break
        return titles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_kr_titles(
    tickers: Iterable[str],
    *,
    http_get: Callable[[str], str] | None = None,
    sleep: Callable[[float], None] | None = None,
    max_per_ticker: int = 3,
) -> list[str]:
    """
    Returns a flat list of news titles collected from Naver finance item
    pages.  Per-ticker failures are logged to stderr and skipped — the
    aggregate still succeeds as long as at least one ticker yielded titles
    (including zero titles is OK; the function never raises).
    """
    fetch = http_get if http_get is not None else _default_kr_http_get
    nap = sleep if sleep is not None else _time.sleep

    ticker_list = list(tickers)
    all_titles: list[str] = []

    for idx, ticker in enumerate(ticker_list):
        ticker_str = str(ticker).zfill(6)
        url = f"https://finance.naver.com/item/main.naver?code={ticker_str}"
        try:
            html = fetch(url)
            titles = _parse_kr_titles(html, max_per_ticker)
            all_titles.extend(t.strip() for t in titles if t.strip())
        except Exception as exc:
            print(
                f"[WARN] news_fetcher: KR ticker {ticker_str} failed: {exc}",
                file=sys.stderr,
            )
        # Sleep between tickers (not after the last one)
        if idx < len(ticker_list) - 1:
            nap(0.5)

    return all_titles


def fetch_us_titles(
    tickers: Iterable[str],
    *,
    http_get: Callable[[str], str] | None = None,
    sleep: Callable[[float], None] | None = None,
    max_per_ticker: int = 3,
) -> list[str]:
    """
    Returns a flat list of US news titles from Naver stock API.
    Per-ticker failures (HTTP, JSON, missing 'items') are logged + skipped.
    Never raises.
    """
    fetch = http_get if http_get is not None else _default_us_http_get
    nap = sleep if sleep is not None else _time.sleep

    ticker_list = list(tickers)
    all_titles: list[str] = []

    for idx, ticker in enumerate(ticker_list):
        url = f"https://api.stock.naver.com/news/stock/{ticker}?pageSize=3&page=1"
        try:
            body = fetch(url)
            data = json.loads(body)
            items = data.get("items")
            if not isinstance(items, list):
                print(
                    f"[WARN] news_fetcher: US ticker {ticker} — 'items' missing or not a list",
                    file=sys.stderr,
                )
                if idx < len(ticker_list) - 1:
                    nap(0.5)
                continue
            for item in items[:max_per_ticker]:
                title = item.get("title", "").strip()
                if title:
                    all_titles.append(title)
        except Exception as exc:
            print(
                f"[WARN] news_fetcher: US ticker {ticker} failed: {exc}",
                file=sys.stderr,
            )
        # Sleep between tickers (not after the last one)
        if idx < len(ticker_list) - 1:
            nap(0.5)

    return all_titles
