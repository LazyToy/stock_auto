import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "backfill_5day_return.py"
    spec = importlib.util.spec_from_file_location("legacy_backfill_5day_return", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_backfill_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.backfill_5day_return")

    assert callable(module.is_backfill_ready)
    assert callable(module.compute_5day_return)
    assert callable(module.backfill_early_signal_returns)



def test_src_crawling_backfill_preserves_pure_logic() -> None:
    module = importlib.import_module("src.crawling.backfill_5day_return")

    assert module.is_backfill_ready("2026-04-10", __import__("datetime").date(2026, 4, 17), 5) is True
    assert round(module.compute_5day_return(100.0, 105.0), 2) == 5.0



def test_legacy_backfill_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.backfill_5day_return")
    legacy_module = _load_legacy_module()

    assert legacy_module.compute_5day_return(100.0, 105.0) == new_module.compute_5day_return(100.0, 105.0)
