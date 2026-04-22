import importlib
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "theme_cluster.py"
    spec = importlib.util.spec_from_file_location("legacy_theme_cluster", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _sample_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "A", "sector": "2차전지", "change": 7.0, "amount": 100e8},
        {"ticker": "B", "sector": "2차전지", "change": 6.0, "amount": 200e8},
        {"ticker": "C", "sector": "2차전지", "change": 8.0, "amount": 150e8},
    ])



def _sample_sector_map() -> dict[str, str]:
    return {"A": "2차전지", "B": "2차전지", "C": "2차전지"}



def _sample_news() -> dict[str, list[str]]:
    return {
        "A": ["리튬 수주 호재"],
        "B": ["ESS 계약"],
        "C": ["유럽 관세 리스크 해소"],
    }



def test_src_crawling_theme_cluster_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.theme_cluster")

    assert callable(module.compute_intensity)
    assert callable(module.build_theme_clusters)
    assert callable(module.cluster_to_sheet_row)



def test_src_crawling_theme_cluster_preserves_cluster_logic() -> None:
    module = importlib.import_module("src.crawling.theme_cluster")

    clusters = module.build_theme_clusters(_sample_df(), sector_map=_sample_sector_map(), news_titles_by_ticker=_sample_news())

    assert len(clusters) == 1
    assert clusters[0]["sector"] == "2차전지"
    assert clusters[0]["direction"] == "up"



def test_legacy_theme_cluster_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.theme_cluster")
    legacy_module = _load_legacy_module()
    df = _sample_df()
    sector_map = _sample_sector_map()
    news = _sample_news()

    assert legacy_module.compute_intensity(3, 7.0) == new_module.compute_intensity(3, 7.0)
    assert legacy_module.build_theme_clusters(df, sector_map=sector_map, news_titles_by_ticker=news) == new_module.build_theme_clusters(df, sector_map=sector_map, news_titles_by_ticker=news)
    cluster = new_module.build_theme_clusters(df, sector_map=sector_map, news_titles_by_ticker=news)[0]
    assert legacy_module.cluster_to_sheet_row("2026-04-16", cluster) == new_module.cluster_to_sheet_row("2026-04-16", cluster)
