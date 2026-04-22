import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "news_aggregator.py"
    spec = importlib.util.spec_from_file_location("legacy_news_aggregator", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _sample_titles() -> list[str]:
    return [
        "삼성전자 반도체 실적 호조에 외국인 매수 쇄도",
        "SK하이닉스 HBM 수요 급증, 반도체 업황 회복 신호",
        "반도체 대장주 강세, 코스피 2700 돌파",
        "외국인 순매수 지속, 반도체 중심 랠리",
    ]



def test_src_crawling_news_aggregator_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.news_aggregator")

    assert callable(module.extract_keywords)
    assert callable(module.build_gemini_prompt)
    assert callable(module.summarize_narrative)



def test_src_crawling_news_aggregator_preserves_keyword_logic() -> None:
    module = importlib.import_module("src.crawling.news_aggregator")

    keywords = module.extract_keywords(_sample_titles(), top_n=5)

    assert keywords[0] == ("반도체", 4)
    assert any(token == "외국인" for token, _ in keywords)



def test_legacy_news_aggregator_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.news_aggregator")
    legacy_module = _load_legacy_module()

    assert legacy_module.DEFAULT_STOPWORDS_KR == new_module.DEFAULT_STOPWORDS_KR
    assert legacy_module.extract_keywords(_sample_titles(), top_n=5) == new_module.extract_keywords(_sample_titles(), top_n=5)
    assert legacy_module.build_gemini_prompt([("반도체", 4)], [("nvidia", 3)]) == new_module.build_gemini_prompt([("반도체", 4)], [("nvidia", 3)])
    assert legacy_module.summarize_narrative([("반도체", 4)], [("nvidia", 3)], gemini_fn=None) == new_module.summarize_narrative([("반도체", 4)], [("nvidia", 3)], gemini_fn=None)
