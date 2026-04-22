import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "theme_trend.py"
    spec = importlib.util.spec_from_file_location("legacy_theme_trend", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _sample_daily_clusters():
    return [
        {"sector": "2차전지", "avg_change": 7.0, "ticker_count": 3, "representatives": ["A", "B", "C"], "keywords_top5": [("리튬", 3)]},
        {"sector": "2차전지", "avg_change": 5.0, "ticker_count": 4, "representatives": ["A", "B", "D"], "keywords_top5": [("유럽", 2)]},
    ]



def test_src_crawling_theme_trend_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.theme_trend")

    assert callable(module.aggregate_weekly)
    assert callable(module.weekly_trend_to_sheet_row)



def test_src_crawling_theme_trend_preserves_aggregate_logic() -> None:
    module = importlib.import_module("src.crawling.theme_trend")

    rows = module.aggregate_weekly(_sample_daily_clusters(), prev_week_frequencies={})

    assert len(rows) == 1
    assert rows[0]["sector"] == "2차전지"
    assert rows[0]["frequency"] == 2
    assert rows[0]["wow_change"] == "NEW"



def test_legacy_theme_trend_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.theme_trend")
    legacy_module = _load_legacy_module()
    rows = _sample_daily_clusters()

    assert legacy_module.aggregate_weekly(rows, prev_week_frequencies={}) == new_module.aggregate_weekly(rows, prev_week_frequencies={})
    assert legacy_module.weekly_trend_to_sheet_row(
        "2026-W16",
        {
            "sector": "IT",
            "frequency": 3,
            "wow_change": "▲ +1",
            "avg_change_pct": 6.5,
            "representatives": ["AAPL", "MSFT"],
            "keywords_top5": [("AI", 5), ("반도체", 3)],
        },
    ) == new_module.weekly_trend_to_sheet_row(
        "2026-W16",
        {
            "sector": "IT",
            "frequency": 3,
            "wow_change": "▲ +1",
            "avg_change_pct": 6.5,
            "representatives": ["AAPL", "MSFT"],
            "keywords_top5": [("AI", 5), ("반도체", 3)],
        },
    )
