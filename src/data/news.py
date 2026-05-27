import logging
from collections.abc import Callable
from typing import Any

from src.crawling.news_fetcher import fetch_kr_news, fetch_us_news

logger = logging.getLogger("NewsFetcher")

NewsItemFetcher = Callable[..., list[dict[str, str]]]


def _normalize_symbol(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _kr_news_symbol(ticker: str) -> str:
    return _normalize_symbol(ticker).split(".", 1)[0].zfill(6)


def _is_kr_symbol(ticker: str) -> bool:
    symbol = _normalize_symbol(ticker).split(".", 1)[0]
    return symbol.isdigit()


class NewsFetcher:
    """심층분석에서 사용할 종목별 뉴스 제목+URL 수집기."""

    def __init__(
        self,
        *,
        fetch_kr_news: NewsItemFetcher = fetch_kr_news,
        fetch_us_news: NewsItemFetcher = fetch_us_news,
    ):
        self._fetch_kr_news = fetch_kr_news
        self._fetch_us_news = fetch_us_news

    def fetch_for_ticker(self, ticker: str, *, limit: int = 3) -> list[dict[str, Any]]:
        symbol = _normalize_symbol(ticker)
        if not symbol or limit <= 0:
            return []

        try:
            if _is_kr_symbol(symbol):
                news_symbol = _kr_news_symbol(symbol)
                fetched_items = self._fetch_kr_news([news_symbol], max_per_ticker=limit)
                source = "Naver Finance"
            else:
                news_symbol = symbol
                fetched_items = self._fetch_us_news([news_symbol], max_per_ticker=limit)
                source = "Naver Stock"
        except Exception as exc:
            logger.warning("뉴스 수집 실패 (%s): %s", symbol, exc)
            return []

        news_items: list[dict[str, Any]] = []
        for item in fetched_items[:limit]:
            clean_title = str(item.get("title", "")).strip()
            if clean_title:
                news_items.append(
                    {
                        "title": clean_title,
                        "url": str(item.get("url", "")).strip(),
                        "source": source,
                        "symbol": news_symbol,
                    }
                )

        return news_items
