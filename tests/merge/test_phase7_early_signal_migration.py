import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "early_signal.py"
    spec = importlib.util.spec_from_file_location("legacy_early_signal", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_early_signal_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.early_signal")

    assert module.EARLY_SIGNAL_HEADERS[0] == "날짜"
    assert callable(module.is_early_signal)
    assert callable(module.build_early_signal_row)



def test_src_crawling_early_signal_preserves_signal_logic() -> None:
    module = importlib.import_module("src.crawling.early_signal")

    assert module.is_early_signal(change=5, rvol=3.0, streak=3, close_ratio_52w=0.5) is True
    assert module.is_early_signal(change=2.5, rvol=3.0, streak=3, close_ratio_52w=0.9) is False



def test_legacy_early_signal_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.early_signal")
    legacy_module = _load_legacy_module()

    assert legacy_module.EARLY_SIGNAL_HEADERS == new_module.EARLY_SIGNAL_HEADERS
    assert legacy_module.is_early_signal(change=5, rvol=3.0, streak=3, close_ratio_52w=0.5) is True
    assert legacy_module.build_early_signal_row(
        date="2026-04-17",
        ticker="005930",
        name="삼성전자",
        change=5.0,
        rvol=3.2,
        streak=3,
        close_ratio_52w=0.96,
        amount=500e8,
    ) == new_module.build_early_signal_row(
        date="2026-04-17",
        ticker="005930",
        name="삼성전자",
        change=5.0,
        rvol=3.2,
        streak=3,
        close_ratio_52w=0.96,
        amount=500e8,
    )
