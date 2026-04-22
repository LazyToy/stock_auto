import importlib
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "daily_trend_writer.py"
    spec = importlib.util.spec_from_file_location("legacy_daily_trend_writer", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _make_kr_snap() -> dict:
    return dict(
        date="2026-04-12",
        total=2721, up=2030, down=447, flat=244,
        breadth=0.5818,
        kospi_breadth=0.5842,
        kosdaq_breadth=0.5805,
        top20_volume_concentration=0.466,
        surge15_count=41, drop15_count=1,
        limit_up=15, limit_down=0,
        cap_weighted_change=1.52,
        top_gainers=pd.DataFrame([{"Code": "005930", "Name": "삼성전자", "Market": "KOSPI", "ChagesRatio": 29.90, "Amount": 1.0e11}]),
        top_losers=pd.DataFrame([{"Code": "111111", "Name": "망한회사", "Market": "KOSDAQ", "ChagesRatio": -18.50, "Amount": 1.0e9}]),
        top_volume=pd.DataFrame([{"Code": "373220", "Name": "LG에너지솔루션", "Market": "KOSPI", "ChagesRatio": 3.20, "Amount": 5.0e12}]),
    )



def test_src_crawling_daily_trend_writer_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.daily_trend_writer")

    assert callable(module.kr_snapshot_to_row)
    assert callable(module.us_snapshot_to_row)
    assert callable(module.format_keywords)



def test_src_crawling_daily_trend_writer_preserves_row_logic() -> None:
    module = importlib.import_module("src.crawling.daily_trend_writer")

    row = module.kr_snapshot_to_row(_make_kr_snap())

    assert row[0] == "2026-04-12"
    assert row[1] == 2721
    assert row[14] == "삼성전자"



def test_legacy_daily_trend_writer_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.daily_trend_writer")
    legacy_module = _load_legacy_module()

    assert legacy_module.kr_snapshot_to_row(_make_kr_snap()) == new_module.kr_snapshot_to_row(_make_kr_snap())
    assert legacy_module.format_keywords([("반도체", 12)]) == new_module.format_keywords([("반도체", 12)])
