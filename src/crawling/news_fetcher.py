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
from html import unescape
from typing import Callable, Iterable
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Chrome-style UA shared by both fetchers
# ---------------------------------------------------------------------------
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_NAVER_FINANCE_BASE_URL = "https://finance.naver.com"

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

def _normalize_kr_news_url(href: str) -> str:
    return urljoin(_NAVER_FINANCE_BASE_URL, href.strip()) if href else ""


def _parse_kr_news(html: str, max_per_ticker: int) -> list[dict[str, str]]:
    """Extract news titles and URLs from a Naver finance item page."""
    if _BS4_AVAILABLE and _BeautifulSoup is not None:
        soup = _BeautifulSoup(html, "html.parser")
        articles = soup.select(".sub_section.news_section ul li a")
        if not articles:
            articles = soup.select(".news_section a")
        news_items: list[dict[str, str]] = []
        for a in articles[:max_per_ticker]:
            title = a.get_text(strip=True)
            url = _normalize_kr_news_url(str(a.get("href") or ""))
            if title:
                news_items.append({"title": title, "url": url})
        return news_items
    else:
        # Regex fallback when bs4 is not installed
        import re
        news_items: list[dict[str, str]] = []
        # Try to narrow to news_section block first
        block_match = re.search(
            r'class=["\'][^"\']*news_section[^"\']*["\'].*?</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        search_area = block_match.group(0) if block_match else html
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', search_area, re.DOTALL | re.IGNORECASE):
            attrs = m.group(1)
            href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            href = unescape(href_match.group(1)) if href_match else ""
            raw = unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
            if raw:
                news_items.append({"title": raw, "url": _normalize_kr_news_url(href)})
            if len(news_items) >= max_per_ticker:
                break
        return news_items


def _parse_kr_titles(html: str, max_per_ticker: int) -> list[str]:
    """Extract news titles from a Naver finance item page."""
    return [item["title"] for item in _parse_kr_news(html, max_per_ticker)]


def _extract_us_items(data: object) -> list[dict]:
    if isinstance(data, dict):
        items = data.get("items")
        return items if isinstance(items, list) else []
    if isinstance(data, list):
        return [
            item
            for group in data
            if isinstance(group, dict)
            for item in group.get("items", [])
            if isinstance(item, dict)
        ]
    return []


def _us_news_url(item: dict, ticker: str) -> str:
    for key in ("url", "link", "newsUrl", "mobileNewsUrl", "articleUrl", "originLink"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    article_id = item.get("articleId")
    office_id = item.get("officeId")
    if article_id and office_id:
        return f"https://m.stock.naver.com/worldstock/stock/{ticker}/news/{article_id}/{office_id}"

    return ""


def _us_ticker_variants(ticker: str) -> list[str]:
    ticker_str = str(ticker).strip().upper()
    if not ticker_str:
        return []
    if "." in ticker_str:
        return [ticker_str]
    return [f"{ticker_str}.O", f"{ticker_str}.N", f"{ticker_str}.A"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_kr_news(
    tickers: Iterable[str],
    *,
    http_get: Callable[[str], str] | None = None,
    sleep: Callable[[float], None] | None = None,
    max_per_ticker: int = 3,
) -> list[dict[str, str]]:
    """
    Returns a flat list of news title+URL items collected from Naver finance item
    pages.  Per-ticker failures are logged to stderr and skipped — the
    function never raises.
    """
    fetch = http_get if http_get is not None else _default_kr_http_get
    nap = sleep if sleep is not None else _time.sleep

    ticker_list = list(tickers)
    all_news: list[dict[str, str]] = []

    for idx, ticker in enumerate(ticker_list):
        ticker_str = str(ticker).zfill(6)
        url = f"https://finance.naver.com/item/main.naver?code={ticker_str}"
        try:
            html = fetch(url)
            news_items = _parse_kr_news(html, max_per_ticker)
            all_news.extend(item for item in news_items if item.get("title", "").strip())
        except Exception as exc:
            print(
                f"[WARN] news_fetcher: KR ticker {ticker_str} failed: {exc}",
                file=sys.stderr,
            )
        # Sleep between tickers (not after the last one)
        if idx < len(ticker_list) - 1:
            nap(0.5)

    return all_news


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
    return [
        item["title"]
        for item in fetch_kr_news(
            tickers,
            http_get=http_get,
            sleep=sleep,
            max_per_ticker=max_per_ticker,
        )
    ]


def fetch_us_news(
    tickers: Iterable[str],
    *,
    http_get: Callable[[str], str] | None = None,
    sleep: Callable[[float], None] | None = None,
    max_per_ticker: int = 3,
) -> list[dict[str, str]]:
    """
    Returns a flat list of US news title+URL items from Naver stock API.
    Per-ticker failures (HTTP, JSON, missing 'items') are logged + skipped.
    Never raises.
    """
    fetch = http_get if http_get is not None else _default_us_http_get
    nap = sleep if sleep is not None else _time.sleep

    ticker_list = list(tickers)
    all_news: list[dict[str, str]] = []

    for idx, ticker in enumerate(ticker_list):
        found_for_ticker = False
        last_error: Exception | None = None
        for variant in _us_ticker_variants(str(ticker)):
            url = f"https://api.stock.naver.com/news/stock/{variant}?pageSize={max_per_ticker}&page=1"
            try:
                body = fetch(url)
                data = json.loads(body)
                items = _extract_us_items(data)
                if not items:
                    continue
                for item in items[:max_per_ticker]:
                    title = str(item.get("title", "")).strip()
                    if title:
                        all_news.append({"title": title, "url": _us_news_url(item, variant)})
                        found_for_ticker = True
                if found_for_ticker:
                    break
            except Exception as exc:
                last_error = exc
        if not found_for_ticker:
            if last_error is not None:
                print(
                    f"[WARN] news_fetcher: US ticker {ticker} failed: {last_error}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[WARN] news_fetcher: US ticker {ticker} — 'items' missing or not a list",
                    file=sys.stderr,
                )
        # Sleep between tickers (not after the last one)
        if idx < len(ticker_list) - 1:
            nap(0.5)

    return all_news


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
    return [
        item["title"]
        for item in fetch_us_news(
            tickers,
            http_get=http_get,
            sleep=sleep,
            max_per_ticker=max_per_ticker,
        )
    ]
