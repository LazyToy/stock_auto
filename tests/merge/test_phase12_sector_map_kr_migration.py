import importlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "sector_map_kr.py"
    spec = importlib.util.spec_from_file_location("legacy_sector_map_kr", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_sector_map_kr_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.sector_map_kr")

    assert hasattr(module, "SectorMapKR")
    assert hasattr(module, "UNKNOWN_SECTOR")
    assert hasattr(module, "CACHE_MAX_AGE_DAYS")
    assert hasattr(module, "MIN_COVERAGE")



def test_src_crawling_sector_map_kr_preserves_cache_logic() -> None:
    module = importlib.import_module("src.crawling.sector_map_kr")

    with TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "map.json"
        cache_path.write_text(json.dumps({"fetched_at": "2026-04-01", "data": {"005930": "반도체"}}, ensure_ascii=False), encoding="utf-8")
        sm = module.SectorMapKR(str(cache_path), fetcher=lambda: {"005930": "새값"}, clock=lambda: datetime(2026, 4, 13))
        loaded = sm.load()

    assert loaded["005930"] == "반도체"
    assert sm.lookup("5930") == "반도체"



def test_legacy_sector_map_kr_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.sector_map_kr")
    legacy_module = _load_legacy_module()

    assert legacy_module.UNKNOWN_SECTOR == new_module.UNKNOWN_SECTOR
    assert legacy_module.CACHE_MAX_AGE_DAYS == new_module.CACHE_MAX_AGE_DAYS
    assert legacy_module.MIN_COVERAGE == new_module.MIN_COVERAGE
