import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "backtest_early_signal.py"
    spec = importlib.util.spec_from_file_location("legacy_backtest_early_signal", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_backtest_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.backtest_early_signal")

    assert callable(module.compute_horizon_returns)
    assert callable(module.summarize_returns)
    assert callable(module.compute_surge_hit_rate)



def test_src_crawling_backtest_preserves_pure_logic() -> None:
    module = importlib.import_module("src.crawling.backtest_early_signal")

    summary = module.summarize_returns([-10.0, 0.0, 10.0, 20.0])

    assert summary["count"] == 4
    assert summary["win_rate"] == 0.5



def test_legacy_backtest_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.backtest_early_signal")
    legacy_module = _load_legacy_module()

    assert legacy_module.compute_surge_hit_rate([{"max_return_5d": 16.0}, {"max_return_5d": 5.0}], threshold=15.0) == new_module.compute_surge_hit_rate([{"max_return_5d": 16.0}, {"max_return_5d": 5.0}], threshold=15.0)
