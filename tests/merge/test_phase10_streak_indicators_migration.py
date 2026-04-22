import importlib
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "streak_indicators.py"
    spec = importlib.util.spec_from_file_location("legacy_streak_indicators", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _sample_ohlc() -> pd.DataFrame:
    rows = [(100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i) for i in range(15)]
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx, columns=pd.Index(["Open", "High", "Low", "Close"]))



def test_src_crawling_streak_indicators_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.streak_indicators")

    assert callable(module.is_52w_high)
    assert callable(module.is_52w_low)
    assert callable(module.current_streak)
    assert callable(module.atr14)
    assert callable(module.compute_indicators)



def test_src_crawling_streak_indicators_preserves_indicator_logic() -> None:
    module = importlib.import_module("src.crawling.streak_indicators")
    df = _sample_ohlc()

    indicators = module.compute_indicators(df)

    assert indicators["is_52w_high"] is True
    assert indicators["is_52w_low"] is False
    assert indicators["streak_days"] > 0
    assert indicators["atr14"] == 2.0



def test_legacy_streak_indicators_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.streak_indicators")
    legacy_module = _load_legacy_module()
    df = _sample_ohlc()

    assert legacy_module.is_52w_high(df) == new_module.is_52w_high(df)
    assert legacy_module.is_52w_low(df) == new_module.is_52w_low(df)
    assert legacy_module.current_streak(df) == new_module.current_streak(df)
    assert legacy_module.atr14(df) == new_module.atr14(df)
    assert legacy_module.compute_indicators(df) == new_module.compute_indicators(df)
