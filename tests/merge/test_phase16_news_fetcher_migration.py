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
US_JSON = '{"items":[{"title":"NVDA record earnings"},{"title":"AI boom continues"}]}'


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



def test_src_crawling_news_fetcher_preserves_fetch_logic() -> None:
    module = importlib.import_module("src.crawling.news_fetcher")

    kr_titles = module.fetch_kr_titles(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2)
    us_titles = module.fetch_us_titles(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2)

    assert kr_titles == ["삼성전자 신제품 발표", "반도체 업황 회복 신호"]
    assert us_titles == ["NVDA record earnings", "AI boom continues"]



def test_legacy_news_fetcher_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.news_fetcher")
    legacy_module = _load_legacy_module()

    assert legacy_module.fetch_kr_titles(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2) == new_module.fetch_kr_titles(["005930"], http_get=lambda _: KR_HTML, sleep=lambda _: None, max_per_ticker=2)
    assert legacy_module.fetch_us_titles(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2) == new_module.fetch_us_titles(["NVDA"], http_get=lambda _: US_JSON, sleep=lambda _: None, max_per_ticker=2)
