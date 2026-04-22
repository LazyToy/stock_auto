import importlib
import sys
from types import ModuleType, SimpleNamespace

import pandas as pd



def _install_stock_scraper_import_stubs(monkeypatch) -> None:
    bs4_module = ModuleType("bs4")
    setattr(bs4_module, "BeautifulSoup", object)

    gspread_module = ModuleType("gspread")
    setattr(gspread_module, "authorize", lambda credentials: SimpleNamespace())

    credentials_cls = type("Credentials", (), {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())})
    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)

    fdr_module = ModuleType("FinanceDataReader")
    sector_map_module = ModuleType("src.crawling.sector_map_kr")
    setattr(sector_map_module, "SectorMapKR", object)

    monkeypatch.setitem(sys.modules, "bs4", bs4_module)
    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)



def test_src_crawling_stock_scraper_exports_expected_api(monkeypatch) -> None:
    _install_stock_scraper_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.stock_scraper")

    assert callable(module.infer_volume_unit)
    assert callable(module.resolve_trading_date)
    assert callable(module.main)



def test_src_crawling_stock_scraper_preserves_volume_unit_logic(monkeypatch) -> None:
    _install_stock_scraper_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.stock_scraper")
    df = pd.DataFrame([{"Code": "005930", "Amount": 5_000.0}])

    multiplier = module.infer_volume_unit(df)

    assert multiplier == 1_000_000



def test_src_crawling_stock_scraper_dry_run_mock_skips_google_auth(monkeypatch, capsys) -> None:
    _install_stock_scraper_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.stock_scraper")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setattr(module, "get_gspread_client", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("google auth called")))

    class _FakeSectorMap:
        def lookup(self, ticker: str) -> str:
            return "반도체"

    monkeypatch.setattr(module, "SectorMapKR", lambda *args, **kwargs: SimpleNamespace(load=lambda **kw: None, lookup=_FakeSectorMap().lookup))

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN OK]" in captured.out
