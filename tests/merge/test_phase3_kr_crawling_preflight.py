import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4


def _load_module_from_path(module_path: Path):
    module_name = f"phase3_{module_path.stem}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_kr_scraper_import_stubs(monkeypatch) -> None:
    bs4_module = ModuleType("bs4")
    setattr(bs4_module, "BeautifulSoup", object)

    gspread_module = ModuleType("gspread")
    exceptions = ModuleType("gspread.exceptions")
    setattr(exceptions, "SpreadsheetNotFound", type("SpreadsheetNotFound", (Exception,), {}))
    setattr(exceptions, "WorksheetNotFound", type("WorksheetNotFound", (Exception,), {}))
    setattr(gspread_module, "exceptions", exceptions)

    credentials_cls = type(
        "Credentials",
        (),
        {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())},
    )
    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)

    pandas_module = ModuleType("pandas")
    setattr(pandas_module, "DataFrame", lambda *args, **kwargs: object())
    setattr(pandas_module, "to_numeric", lambda *args, **kwargs: object())

    fdr_module = ModuleType("FinanceDataReader")

    sector_map_module = ModuleType("sector_map_kr")

    class _DummySectorMapKR:
        def __init__(self, *args, **kwargs):
            pass

        def load(self, **kwargs):
            return None

    setattr(sector_map_module, "SectorMapKR", _DummySectorMapKR)

    streak_module = ModuleType("streak_indicators")
    setattr(streak_module, "compute_indicators", lambda *args, **kwargs: {})

    monkeypatch.setitem(sys.modules, "bs4", bs4_module)
    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "gspread.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "pandas", pandas_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)
    monkeypatch.setitem(sys.modules, "sector_map_kr", sector_map_module)
    monkeypatch.setitem(sys.modules, "streak_indicators", streak_module)


def _load_kr_scraper(monkeypatch):
    _install_kr_scraper_import_stubs(monkeypatch)
    return _load_module_from_path(
        Path(r"D:\HY\develop_Project\stock_auto\stock_crawling\stock_scraper.py")
    )


def _patch_mock_dry_run_dependencies(module, monkeypatch) -> None:
    monkeypatch.setattr(module, "dry_run_indicator_check", lambda *args, **kwargs: print("[DRY RUN OK] len=20 header=20 match=YES"))



def test_stock_scraper_dry_run_mock_skips_google_auth(monkeypatch, capsys):
    module = _load_kr_scraper(monkeypatch)
    _patch_mock_dry_run_dependencies(module, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setattr(
        module,
        "get_gspread_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("google auth called")),
    )

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out
    assert "MOCK(no network)" in captured.out



def test_stock_scraper_dry_run_mock_emits_kr_preflight_banner(monkeypatch, capsys):
    module = _load_kr_scraper(monkeypatch)
    _patch_mock_dry_run_dependencies(module, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN OK] KR preflight completed" in captured.out



def test_stock_scraper_dry_run_mock_keeps_indicator_check_and_completion_banner(monkeypatch, capsys):
    module = _load_kr_scraper(monkeypatch)
    _patch_mock_dry_run_dependencies(module, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN OK] len=20 header=20 match=YES" in captured.out
    assert "KR preflight completed" in captured.out
