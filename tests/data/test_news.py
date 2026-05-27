from unittest.mock import MagicMock

from src.data.news import NewsFetcher


def test_fetch_for_ticker_uses_kr_news_fetcher_for_kr_symbol():
    kr_fetcher = MagicMock(
        return_value=[
            {"title": "삼성전자 실적 개선", "url": "https://finance.naver.com/news/1"},
            {"title": "반도체 업황 회복", "url": "https://finance.naver.com/news/2"},
        ]
    )
    us_fetcher = MagicMock(return_value=[])
    fetcher = NewsFetcher(fetch_kr_news=kr_fetcher, fetch_us_news=us_fetcher)

    news = fetcher.fetch_for_ticker("005930.KS", limit=2)

    kr_fetcher.assert_called_once_with(["005930"], max_per_ticker=2)
    us_fetcher.assert_not_called()
    assert news == [
        {
            "title": "삼성전자 실적 개선",
            "url": "https://finance.naver.com/news/1",
            "source": "Naver Finance",
            "symbol": "005930",
        },
        {
            "title": "반도체 업황 회복",
            "url": "https://finance.naver.com/news/2",
            "source": "Naver Finance",
            "symbol": "005930",
        },
    ]


def test_fetch_for_ticker_uses_us_news_fetcher_for_us_symbol():
    kr_fetcher = MagicMock(return_value=[])
    us_fetcher = MagicMock(
        return_value=[
            {"title": "Apple announces new AI chip", "url": "https://m.stock.naver.com/worldstock/news/1"}
        ]
    )
    fetcher = NewsFetcher(fetch_kr_news=kr_fetcher, fetch_us_news=us_fetcher)

    news = fetcher.fetch_for_ticker("AAPL", limit=4)

    us_fetcher.assert_called_once_with(["AAPL"], max_per_ticker=4)
    kr_fetcher.assert_not_called()
    assert news == [
        {
            "title": "Apple announces new AI chip",
            "url": "https://m.stock.naver.com/worldstock/news/1",
            "source": "Naver Stock",
            "symbol": "AAPL",
        },
    ]


def test_fetch_for_ticker_returns_empty_when_limit_is_zero():
    kr_fetcher = MagicMock(return_value=["ignored"])
    us_fetcher = MagicMock(return_value=["ignored"])
    fetcher = NewsFetcher(fetch_kr_news=kr_fetcher, fetch_us_news=us_fetcher)

    assert fetcher.fetch_for_ticker("AAPL", limit=0) == []
    kr_fetcher.assert_not_called()
    us_fetcher.assert_not_called()
