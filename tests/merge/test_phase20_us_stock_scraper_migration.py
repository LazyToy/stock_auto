import importlib
import sys
from types import ModuleType, SimpleNamespace



def _install_us_scraper_import_stubs(monkeypatch) -> None:
    gspread_module = ModuleType("gspread")
    setattr(gspread_module, "SpreadsheetNotFound", type("SpreadsheetNotFound", (Exception,), {}))
    setattr(gspread_module, "WorksheetNotFound", type("WorksheetNotFound", (Exception,), {}))
    setattr(gspread_module, "authorize", lambda credentials: SimpleNamespace(open=lambda name: SimpleNamespace(url=name), create=lambda name: SimpleNamespace(url=name)))

    credentials_cls = type("Credentials", (), {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())})
    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)

    pandas_module = ModuleType("pandas")
    setattr(pandas_module, "DataFrame", object)

    fdr_module = ModuleType("FinanceDataReader")

    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "pandas", pandas_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)



def test_src_crawling_us_stock_scraper_exports_expected_api(monkeypatch) -> None:
    _install_us_scraper_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.us_stock_scraper")

    assert callable(module.make_sheet_month)
    assert callable(module.make_row_date)
    assert callable(module.decode_tv_row)
    assert callable(module.main)



def test_src_crawling_us_stock_scraper_preserves_decode_logic(monkeypatch) -> None:
    _install_us_scraper_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.us_stock_scraper")

    row = module.decode_tv_row(["AAPL", "Apple", 180.0, 5.0, 150000000.0, 181.0, 175.0, 3000000000000.0, "Technology", 1000000.0])

    assert row["ticker"] == "AAPL"
    assert row["close"] == 180.0
    assert row["_sanity_ok"] is True



def test_src_crawling_us_stock_scraper_dry_run_mock_skips_google_auth(monkeypatch, capsys) -> None:
    _install_us_scraper_import_stubs(monkeypatch)
    module = importlib.import_module("src.crawling.us_stock_scraper")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setattr(module, "get_google_sheet", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("google auth called")))

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN OK] US preflight completed" in captured.out
