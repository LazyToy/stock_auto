import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4


def _load_module_from_path(module_path: Path):
    module_name = f"phase2_{module_path.stem}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_us_scraper_import_stubs(monkeypatch) -> None:
    gspread_module = ModuleType("gspread")
    setattr(gspread_module, "SpreadsheetNotFound", type("SpreadsheetNotFound", (Exception,), {}))
    setattr(gspread_module, "WorksheetNotFound", type("WorksheetNotFound", (Exception,), {}))
    setattr(gspread_module, "authorize", lambda credentials: SimpleNamespace())

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
    setattr(pandas_module, "DataFrame", object)

    fdr_module = ModuleType("FinanceDataReader")
    streak_module = ModuleType("streak_indicators")
    setattr(streak_module, "compute_indicators", lambda *args, **kwargs: {})

    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "pandas", pandas_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)
    monkeypatch.setitem(sys.modules, "streak_indicators", streak_module)


def _load_us_scraper(monkeypatch):
    _install_us_scraper_import_stubs(monkeypatch)
    return _load_module_from_path(
        Path(r"D:\HY\develop_Project\stock_auto\stock_crawling\us_stock_scraper.py")
    )


def test_get_google_sheet_returns_none_with_clear_message_when_credentials_missing(monkeypatch, capsys):
    module = _load_us_scraper(monkeypatch)

    def _raise_missing_credentials(*args, **kwargs):
        raise FileNotFoundError("missing service account")

    monkeypatch.setattr(
        module.Credentials,
        "from_service_account_file",
        staticmethod(_raise_missing_credentials),
    )

    sheet = module.get_google_sheet("202604")

    captured = capsys.readouterr()
    assert sheet is None
    assert "구글 시트 인증/생성 에러" in captured.out
    assert "missing service account" in captured.out


def test_us_stock_scraper_dry_run_mock_skips_google_auth(monkeypatch, capsys):
    module = _load_us_scraper(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setattr(
        module,
        "get_google_sheet",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("google auth called")),
    )

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out
    assert "MOCK(no network)" in captured.out


def test_us_stock_scraper_dry_run_mock_emits_success_banner(monkeypatch, capsys):
    module = _load_us_scraper(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("MOCK", "1")

    module.main()

    captured = capsys.readouterr()
    assert "[DRY RUN OK]" in captured.out
    assert "US preflight completed" in captured.out
