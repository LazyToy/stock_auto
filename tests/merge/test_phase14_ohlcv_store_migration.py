import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "ohlcv_store.py"
    spec = importlib.util.spec_from_file_location("legacy_ohlcv_store", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_ohlcv_store_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.ohlcv_store")

    assert hasattr(module, "OHLCVStore")
    assert callable(module.compute_avg_volume)



def test_src_crawling_ohlcv_store_preserves_storage_logic() -> None:
    module = importlib.import_module("src.crawling.ohlcv_store")
    store = module.OHLCVStore(":memory:")
    try:
        for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300)]:
            store.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
        assert store.avg_volume("005930", window=3) == 200.0
    finally:
        store.close()



def test_legacy_ohlcv_store_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.ohlcv_store")
    legacy_module = _load_legacy_module()

    new_store = new_module.OHLCVStore(":memory:")
    legacy_store = legacy_module.OHLCVStore(":memory:")
    try:
        for store in (new_store, legacy_store):
            for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300)]:
                store.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
        assert legacy_store.avg_volume("005930", window=3) == new_store.avg_volume("005930", window=3)
    finally:
        new_store.close()
        legacy_store.close()
