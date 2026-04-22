import importlib
import importlib.util
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "generate_snapshots.py"
    spec = importlib.util.spec_from_file_location("legacy_generate_snapshots", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _kr_fixture() -> dict:
    return {"date": "2026-04-13", "total": 1, "up": 1, "down": 0, "flat": 0, "breadth": 1.0, "kospi_breadth": 1.0, "kosdaq_breadth": 1.0, "top20_volume_concentration": 0.1, "surge15_count": 0, "drop15_count": 0, "limit_up": 0, "limit_down": 0, "cap_weighted_change": 1.0, "top_gainers": None, "top_losers": None, "top_volume": None}



def _us_fixture() -> dict:
    return {"date": "2026-04-13", "total": 1, "up": 1, "down": 0, "flat": 0, "breadth": 1.0, "cap_weighted_change": 1.0, "surge8_count": 0, "drop8_count": 0, "top_gainers": None, "top_losers": None, "top_volume": None, "sectors": None}



class _FakeSheet:
    def __init__(self, year: int) -> None:
        self.year = year
        self.kr_calls = []
        self.us_calls = []

    def append_kr_snapshot(self, snap: dict) -> bool:
        self.kr_calls.append(snap)
        return True

    def append_us_snapshot(self, snap: dict) -> bool:
        self.us_calls.append(snap)
        return True



def test_src_crawling_generate_snapshots_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.generate_snapshots")

    assert callable(module.run_snapshots)
    assert callable(module._last_iso_week)



def test_src_crawling_generate_snapshots_preserves_happy_path() -> None:
    module = importlib.import_module("src.crawling.generate_snapshots")
    sheets = []

    def factory(year: int):
        s = _FakeSheet(year)
        sheets.append(s)
        return s

    rc = module.run_snapshots(_kr_fixture, _us_fixture, factory, clock=lambda: datetime(2026, 4, 13))

    assert rc == 0
    assert sheets[0].year == 2026
    assert len(sheets[0].kr_calls) == 1
    assert len(sheets[0].us_calls) == 1



def test_legacy_generate_snapshots_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.generate_snapshots")
    legacy_module = _load_legacy_module()

    assert legacy_module._last_iso_week(datetime(2026, 4, 19)) == new_module._last_iso_week(datetime(2026, 4, 19))
