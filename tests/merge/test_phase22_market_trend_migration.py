import importlib
import importlib.util
from pathlib import Path

import pandas as pd

import sys
from types import ModuleType


def _install_market_trend_import_stubs(monkeypatch) -> None:
    gspread_module = ModuleType("gspread")
    credentials_cls = type("Credentials", (), {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())})
    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)
    pandas_module = ModuleType("pandas")
    import pandas as real_pd
    setattr(pandas_module, "DataFrame", real_pd.DataFrame)
    setattr(pandas_module, "Series", real_pd.Series)
    setattr(pandas_module, "to_numeric", real_pd.to_numeric)
    fdr_module = ModuleType("FinanceDataReader")

    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)




ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "market_trend.py"
    spec = importlib.util.spec_from_file_location("legacy_market_trend", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _sample_us_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "AAPL", "name": "Apple", "change": 5.0, "volume": 1000.0, "volume_value": 200000000.0, "sector": "Technology", "market_cap": 3_000_000_000_000.0, "close": 180.0},
        {"ticker": "NVDA", "name": "Nvidia", "change": -2.0, "volume": 900.0, "volume_value": 180000000.0, "sector": "Technology", "market_cap": 2_000_000_000_000.0, "close": 900.0},
    ])



def test_src_crawling_market_trend_exports_expected_api(monkeypatch) -> None:
    _install_market_trend_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.market_trend")

    assert hasattr(module, "Report")
    assert callable(module.us_trend_snapshot)



def test_src_crawling_market_trend_preserves_us_snapshot_logic(monkeypatch) -> None:
    _install_market_trend_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.market_trend")

    snap = module.us_trend_snapshot(_sample_us_df())

    assert snap["total"] == 2
    assert snap["up"] == 1
    assert snap["down"] == 1



def test_legacy_market_trend_shim_matches_new_module(monkeypatch) -> None:
    _install_market_trend_import_stubs(monkeypatch)
    new_module = importlib.import_module("src.crawling.market_trend")
    legacy_module = _load_legacy_module()

    assert legacy_module.us_trend_snapshot(_sample_us_df())["total"] == new_module.us_trend_snapshot(_sample_us_df())["total"]
