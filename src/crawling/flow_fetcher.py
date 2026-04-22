"""
이슈 #11: 외국인/기관 순매매 수급 데이터 수집.

네이버 finance frgn.naver 페이지에서 외국인·기관 순매매 파싱.
네트워크 호출은 http_get injectable 로 분리.
대량 크롤링 방지: 기본 sleep 0.5초 (초당 2회 이하).
"""
from __future__ import annotations

import re
import time
import urllib.request
from typing import Callable


_DEFAULT_SLEEP = 0.5


def _default_http_get(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible)"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("euc-kr", errors="replace")


def _parse_number(text: str) -> int:
    """'+15,234' → 15234, '-3,100' → -3100, '-' or '' → 0."""
    if not text:
        return 0
    cleaned = text.replace(",", "").replace("+", "").replace("\xa0", "").strip()
    if not cleaned or cleaned == "-":
        return 0
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _text(cell) -> str:
    return cell.get_text(" ", strip=True) if cell is not None else ""


def parse_foreign_institutional_flow(html: str | None) -> list[dict]:
    """
    네이버 frgn.naver HTML 에서 날짜별 외국인/기관 순매매 파싱.

    Parameters
    ----------
    html : str | None
        frgn.naver 페이지 HTML 원문. None 또는 테이블 없으면 빈 리스트 반환.

    Returns
    -------
    list[dict] with keys: date(str), foreign(int), institution(int)
    결과는 최신 날짜 먼저 (HTML 순서 그대로).
    """
    if not html:
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")
        records: list[dict] = []
        for table in soup.find_all("table", class_="type2"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if not cells:
                    continue

                date_idx = -1
                date_text = ""
                for idx, cell in enumerate(cells):
                    value = _text(cell)
                    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", value):
                        date_idx = idx
                        date_text = value
                        break
                if date_idx < 0:
                    continue

                tail = cells[date_idx + 1:]
                # Current Naver layout:
                # date, close, diff, change%, volume, institution net, foreign net, holdings, rate.
                if len(tail) >= 6:
                    institution_text = _text(tail[4])
                    foreign_text = _text(tail[5])
                else:
                    # Legacy/minimal fixture layout:
                    # date, foreign net, institution net.
                    num_tds = row.find_all("td", class_="num")
                    if len(num_tds) < 2:
                        continue
                    foreign_text = _text(num_tds[0])
                    institution_text = _text(num_tds[1])

                records.append({
                    "date": date_text,
                    "foreign": _parse_number(foreign_text),
                    "institution": _parse_number(institution_text),
                })
        return records
    except Exception:
        return []


def fetch_flow(
    ticker: str,
    http_get: Callable[[str], str] = _default_http_get,
    sleep: Callable[[float], None] = time.sleep,
    sleep_sec: float = _DEFAULT_SLEEP,
) -> list[dict]:
    """
    종목 1개의 외국인/기관 순매매 이력 조회.

    sleep_sec 간격으로 요청 (기본 0.5초 — 초당 2회 이하).
    """
    url = f"https://finance.naver.com/item/frgn.naver?code={ticker}"
    html = http_get(url)
    sleep(sleep_sec)
    return parse_foreign_institutional_flow(html)


def fetch_flow_batch(
    tickers: list[str],
    http_get: Callable[[str], str] = _default_http_get,
    sleep: Callable[[float], None] = time.sleep,
    sleep_sec: float = _DEFAULT_SLEEP,
) -> dict[str, list[dict]]:
    """여러 종목 순매매 이력을 {ticker: records} dict 로 반환."""
    result: dict[str, list[dict]] = {}
    for ticker in tickers:
        result[ticker] = fetch_flow(
            ticker, http_get=http_get, sleep=sleep, sleep_sec=sleep_sec
        )
    return result
