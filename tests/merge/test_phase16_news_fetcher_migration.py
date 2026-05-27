import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

KR_HTML = """
<html><body>
<div class="sub_section news_section"><ul>
<li><a href="/news/1">삼성전자 신제품 발표</a></li>
<li><a href="/news/2">반도체 업황 회복 신호</a></li>
<li><a href="/news/3">외국인 순매수 지속</a></li>
</ul></div>
</body></html>
"""
US_JSON = '{"items":[{"title":"NVDA record earnings","url":"https://news.example/nvda"},{"title":"AI boom continues","mobileNewsUrl":"https://m.example/ai"}]}'


def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "news_fetcher.py"
    spec = importlib.util.spec_from_file_location("legacy_news_fetcher", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_news_fetcher_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.news_fetcher")

    assert callable(module.fetch_kr_titles)
    assert callable(module.fetch_us_titles)
    assert callable(module.fetch_kr_news)
    assert callable(module.fetch_us_news)



def test_src_crawling_news_fetcher_preserves_fetch_logic() -> None:
    module = importlib.import_module("src.crawling.news_fetcher")

    kr_titles = module.fetch_kr_titles(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2)
    us_titles = module.fetch_us_titles(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2)

    assert kr_titles == ["삼성전자 신제품 발표", "반도체 업황 회복 신호"]
    assert us_titles == ["NVDA record earnings", "AI boom continues"]

    kr_news = module.fetch_kr_news(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2)
    us_news = module.fetch_us_news(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2)

    assert kr_news == [
        {"title": "삼성전자 신제품 발표", "url": "https://finance.naver.com/news/1"},
        {"title": "반도체 업황 회복 신호", "url": "https://finance.naver.com/news/2"},
    ]
    assert us_news == [
        {"title": "NVDA record earnings", "url": "https://news.example/nvda"},
        {"title": "AI boom continues", "url": "https://m.example/ai"},
    ]


def test_src_crawling_news_fetcher_tries_us_exchange_suffixes() -> None:
    module = importlib.import_module("src.crawling.news_fetcher")
    calls: list[str] = []

    def fake_http_get(url: str) -> str:
        calls.append(url)
        if "AAPL.O" in url:
            return '{"items":[{"title":"Apple suffix news","mobileNewsUrl":"https://m.example/aapl"}]}'
        return '{"items":[]}'

    news = module.fetch_us_news(["AAPL"], http_get=fake_http_get, sleep=lambda _: None, max_per_ticker=3)

    assert news == [{"title": "Apple suffix news", "url": "https://m.example/aapl"}]
    assert len(calls) == 1
    assert "AAPL.O" in calls[0]



def test_legacy_news_fetcher_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.news_fetcher")
    legacy_module = _load_legacy_module()

    assert legacy_module.fetch_kr_titles(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2) == new_module.fetch_kr_titles(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2)
    assert legacy_module.fetch_us_titles(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2) == new_module.fetch_us_titles(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2)
