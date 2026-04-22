"""
KR sector map with auto-refreshing cache.

Public surface
--------------
* ``SectorMapKR`` — cache-aware sector lookup (testable with a fake fetcher).
* ``UNKNOWN_SECTOR`` — bucket name used for tickers missing from the map.
* ``CACHE_MAX_AGE_DAYS`` / ``MIN_COVERAGE`` — refresh policy constants.
* ``default_fetcher`` — production fetcher that scrapes Naver WICS sector
  group pages. Not exercised by the unit test; it is validated by
  ``probe_sector_naver_live.py``.

Refresh policy
--------------
The cache (``sector_map_kr.json``) is refreshed when any of:
  1. the file is missing or unparseable,
  2. the last successful fetch is older than ``CACHE_MAX_AGE_DAYS`` days,
  3. the caller supplies ``known_tickers`` and fewer than ``MIN_COVERAGE``
     of them are present in the cache.
If the fetcher raises and a cache is available, the stale cache is returned
and a warning is printed. If the fetcher raises with no cache, the error
propagates to the caller (no silent empty map).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Callable, Iterable

UNKNOWN_SECTOR = "기타"
CACHE_MAX_AGE_DAYS = 30
MIN_COVERAGE = 0.95

_CACHE_DATE_FMT = "%Y-%m-%d"


def _normalize_key(ticker: Any) -> str:
    return str(ticker).zfill(6)


class SectorMapKR:
    """
    Cache-aware sector lookup.

    Parameters
    ----------
    cache_path : str
        Path to the JSON cache file. Created on first successful fetch.
    fetcher : callable, optional
        Zero-argument callable returning a ``{ticker: sector}`` dict.
        Defaults to :func:`default_fetcher`.
    clock : callable, optional
        Zero-argument callable returning a ``datetime``. Injectable so
        tests can freeze "now".
    """

    def __init__(
        self,
        cache_path: str,
        fetcher: Callable[[], dict[str, str]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache_path = cache_path
        self._fetcher = fetcher if fetcher is not None else default_fetcher
        self._clock = clock if clock is not None else datetime.now
        self._data: dict[str, str] | None = None

    # -- public ------------------------------------------------------------

    def load(self, known_tickers: Iterable[str] | None = None) -> dict[str, str]:
        """
        Return the sector map, refreshing the cache when policy requires it.

        Parameters
        ----------
        known_tickers : iterable of str, optional
            If provided, coverage is checked against this set and the cache
            is refreshed when coverage falls below ``MIN_COVERAGE``.
        """
        cache = self._read_cache()
        known_set: set[str] | None = (
            {_normalize_key(t) for t in known_tickers}
            if known_tickers is not None else None
        )

        should_refresh = (
            cache is None
            or self._is_stale(cache.get("fetched_at", ""))
            or (
                known_set is not None
                and self._coverage(cache.get("data", {}), known_set) < MIN_COVERAGE
            )
        )

        if not should_refresh:
            assert cache is not None
            self._data = self._normalize_data(cache["data"])
            return self._data

        try:
            fresh = self._fetcher()
        except Exception as e:
            if cache is not None:
                print(
                    f"[WARN] sector_map_kr: fetcher failed ({e}); "
                    f"falling back to cached snapshot at {cache.get('fetched_at')}",
                    file=sys.stderr,
                )
                self._data = self._normalize_data(cache["data"])
                return self._data
            raise

        self._data = self._normalize_data(fresh)
        self._write_cache(self._data)
        return self._data

    def lookup(self, ticker: str) -> str:
        """Return the sector for ``ticker``, or ``UNKNOWN_SECTOR`` if missing."""
        if self._data is None:
            self.load()
        assert self._data is not None
        return self._data.get(_normalize_key(ticker), UNKNOWN_SECTOR)

    def classify(self, tickers: Iterable[str]) -> dict[str, str]:
        """Return ``{ticker: sector}`` for the given tickers (unknown → 기타)."""
        if self._data is None:
            self.load()
        assert self._data is not None
        return {
            t: self._data.get(_normalize_key(t), UNKNOWN_SECTOR)
            for t in tickers
        }

    # -- cache helpers -----------------------------------------------------

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(payload, dict) or "data" not in payload:
            return None
        return payload

    def _write_cache(self, data: dict[str, str]) -> None:
        payload = {
            "fetched_at": self._clock().strftime(_CACHE_DATE_FMT),
            "data": data,
        }
        os.makedirs(os.path.dirname(os.path.abspath(self._cache_path)) or ".",
                    exist_ok=True)
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _is_stale(self, fetched_at: str) -> bool:
        try:
            when = datetime.strptime(fetched_at, _CACHE_DATE_FMT)
        except (ValueError, TypeError):
            return True
        return (self._clock() - when).days > CACHE_MAX_AGE_DAYS

    @staticmethod
    def _coverage(data: dict[str, str], known: set[str]) -> float:
        if not known:
            return 1.0
        hit = sum(1 for t in known if t in data)
        return hit / len(known)

    @staticmethod
    def _normalize_data(data: dict[str, Any]) -> dict[str, str]:
        return {_normalize_key(k): str(v) for k, v in data.items()}


# ---------------------------------------------------------------------------
# Production fetchers (not unit-tested — validated by a live probe)
# ---------------------------------------------------------------------------

def default_fetcher() -> dict[str, str]:
    return _fetch_naver()


_NAVER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_NAVER_INDEX_URL = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
_NAVER_DETAIL_URL = (
    "https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={no}"
)
_NAVER_SLEEP_SEC = 0.2

import re as _re
from typing import Callable as _Callable


def _parse_naver_sector_list(html: str) -> list[tuple[str, str]]:
    """
    Parse Naver's ``sise_group.naver?type=upjong`` index page into a list
    of ``(sector_no, sector_name)`` pairs. Order is preserved.

    Uses BeautifulSoup when available; falls back to a regex scan so the
    function stays pure and testable without an optional dependency.
    """
    sectors: list[tuple[str, str]] = []
    seen: set[str] = set()

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError:
        BeautifulSoup = None  # type: ignore[assignment]

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href*='sise_group_detail.naver']"):
            href = str(a.get("href", "") or "")
            m = _re.search(r"no=(\d+)", href)
            if not m:
                continue
            no = m.group(1)
            name = a.get_text(strip=True)
            if no and name and no not in seen:
                seen.add(no)
                sectors.append((no, name))
        return sectors

    # Regex fallback: match <a href="...no=NNN...">NAME</a>
    pattern = _re.compile(
        r'<a[^>]*href="[^"]*sise_group_detail\.naver[^"]*no=(\d+)[^"]*"[^>]*>'
        r'([^<]+)</a>',
        _re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        no = m.group(1).strip()
        name = m.group(2).strip()
        if no and name and no not in seen:
            seen.add(no)
            sectors.append((no, name))
    return sectors


def _parse_naver_sector_detail(html: str) -> list[str]:
    """
    Parse a Naver ``sise_group_detail.naver`` page into a deduplicated list
    of 6-digit tickers, preserving first-seen order.
    """
    tickers: list[str] = []
    seen: set[str] = set()

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError:
        BeautifulSoup = None  # type: ignore[assignment]

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href*='/item/main.naver']"):
            href = str(a.get("href", "") or "")
            m = _re.search(r"code=(\d{6})", href)
            if not m:
                continue
            tkr = m.group(1)
            if tkr not in seen:
                seen.add(tkr)
                tickers.append(tkr)
        return tickers

    pattern = _re.compile(
        r'<a[^>]*href="[^"]*/item/main\.naver\?code=(\d{6})[^"]*"',
        _re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        tkr = m.group(1)
        if tkr not in seen:
            seen.add(tkr)
            tickers.append(tkr)
    return tickers


def _default_http_get(url: str) -> str:
    """Production HTTP GET with Naver-friendly UA and EUC-KR decoding."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": _NAVER_UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = res.read()
    try:
        return raw.decode("euc-kr")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _fetch_naver(
    http_get: _Callable[[str], str] | None = None,
    sleep: _Callable[[float], None] | None = None,
) -> dict[str, str]:
    """
    Build a ``{ticker: sector_name}`` map by scraping Naver's WICS sector
    group pages. ``http_get`` and ``sleep`` are injectable so the test
    suite can exercise this without hitting the network.

    A per-detail-page failure is logged and skipped — the other sectors
    still populate the map — but an empty index is fatal.
    """
    import time as _time

    fetch = http_get if http_get is not None else _default_http_get
    nap = sleep if sleep is not None else _time.sleep

    index_html = fetch(_NAVER_INDEX_URL)
    sectors = _parse_naver_sector_list(index_html)
    if not sectors:
        raise RuntimeError("Naver sector index returned zero sectors")

    result: dict[str, str] = {}
    for no, name in sectors:
        url = _NAVER_DETAIL_URL.format(no=no)
        try:
            detail_html = fetch(url)
        except Exception as e:
            print(f"[WARN] sector_map_kr: Naver detail fetch failed for "
                  f"no={no} ({name}): {e}", file=sys.stderr)
            continue
        for tkr in _parse_naver_sector_detail(detail_html):
            result.setdefault(_normalize_key(tkr), name)
        nap(_NAVER_SLEEP_SEC)

    if not result:
        raise RuntimeError("Naver fetch returned zero tickers")
    return result
