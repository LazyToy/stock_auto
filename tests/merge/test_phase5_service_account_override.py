import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4


ROOT = Path(r"D:\HY\develop_Project\stock_auto")
STOCK_CRAWLING = ROOT / "stock_crawling"



def _load_module_from_path(module_path: Path, monkeypatch, prepend_stock_crawling: bool = False):
    module_name = f"phase5_{module_path.stem}_{uuid4().hex}"
    if prepend_stock_crawling:
        monkeypatch.syspath_prepend(str(STOCK_CRAWLING))
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _install_google_stubs(monkeypatch) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    calls: dict[str, list[tuple[str, tuple[str, ...]]]] = {"credentials": []}

    gspread_module = ModuleType("gspread")
    setattr(gspread_module, "SpreadsheetNotFound", type("SpreadsheetNotFound", (Exception,), {}))
    setattr(gspread_module, "WorksheetNotFound", type("WorksheetNotFound", (Exception,), {}))
    setattr(gspread_module, "authorize", lambda credentials: SimpleNamespace(open=lambda name: SimpleNamespace(url=name), create=lambda name: SimpleNamespace(url=name)))

    credentials_cls = type("Credentials", (), {})

    def _from_service_account_file(path: str, scopes):
        calls["credentials"].append((path, tuple(scopes)))
        return object()

    setattr(credentials_cls, "from_service_account_file", staticmethod(_from_service_account_file))

    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)

    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    return calls



def _install_scraper_stubs(monkeypatch) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    calls = _install_google_stubs(monkeypatch)

    bs4_module = ModuleType("bs4")
    setattr(bs4_module, "BeautifulSoup", object)
    pandas_module = ModuleType("pandas")
    setattr(pandas_module, "DataFrame", object)
    fdr_module = ModuleType("FinanceDataReader")
    sector_map_module = ModuleType("sector_map_kr")
    setattr(sector_map_module, "SectorMapKR", object)
    streak_module = ModuleType("streak_indicators")
    setattr(streak_module, "compute_indicators", lambda *args, **kwargs: {})

    monkeypatch.setitem(sys.modules, "bs4", bs4_module)
    monkeypatch.setitem(sys.modules, "pandas", pandas_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)
    monkeypatch.setitem(sys.modules, "sector_map_kr", sector_map_module)
    monkeypatch.setitem(sys.modules, "streak_indicators", streak_module)
    return calls



def test_service_account_resolver_prefers_env(monkeypatch):
    module = _load_module_from_path(STOCK_CRAWLING / "service_account_path.py", monkeypatch)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "secrets/from-env.json")

    resolved = module.resolve_service_account_file()

    assert resolved == str(ROOT / "secrets" / "from-env.json")



def test_service_account_resolver_loads_root_env_file(monkeypatch):
    module = _load_module_from_path(STOCK_CRAWLING / "service_account_path.py", monkeypatch)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    calls: list[Path] = []

    def _fake_load_dotenv(path, override=False):
        calls.append(Path(path))
        monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "config/google_service_account.json")
        return True

    monkeypatch.setattr(module, "load_dotenv", _fake_load_dotenv)

    resolved = module.resolve_service_account_file()

    assert calls == [ROOT / ".env"]
    assert resolved == str(ROOT / "config" / "google_service_account.json")


def test_service_account_resolver_prefers_config_file_before_legacy(monkeypatch, tmp_path):
    module = _load_module_from_path(STOCK_CRAWLING / "service_account_path.py", monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "DEFAULT_SERVICE_ACCOUNT_FILE", tmp_path / "config" / "google_service_account.json")
    monkeypatch.setattr(module, "LEGACY_SERVICE_ACCOUNT_FILE", tmp_path / "service_account.json")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "google_service_account.json").write_text("{}", encoding="utf-8")
    (tmp_path / "service_account.json").write_text("{}", encoding="utf-8")

    resolved = module.resolve_service_account_file()

    assert resolved == str(tmp_path / "config" / "google_service_account.json")



def test_stock_scraper_uses_resolved_service_account_path(monkeypatch):
    calls = _install_scraper_stubs(monkeypatch)
    module = _load_module_from_path(STOCK_CRAWLING / "stock_scraper.py", monkeypatch, prepend_stock_crawling=True)
    monkeypatch.setattr(module, "resolve_service_account_file", lambda: "config/google_service_account.json")

    module.get_gspread_client()

    assert calls["credentials"][-1][0] == "config/google_service_account.json"



def test_us_stock_scraper_uses_resolved_service_account_path(monkeypatch):
    calls = _install_scraper_stubs(monkeypatch)
    module = _load_module_from_path(STOCK_CRAWLING / "us_stock_scraper.py", monkeypatch, prepend_stock_crawling=True)
    monkeypatch.setattr(module, "resolve_service_account_file", lambda: "config/google_service_account.json")

    module.get_google_sheet("202604")

    assert calls["credentials"][-1][0] == "config/google_service_account.json"



def test_daily_trend_writer_uses_resolved_service_account_path(monkeypatch):
    calls = _install_google_stubs(monkeypatch)
    module = _load_module_from_path(STOCK_CRAWLING / "daily_trend_writer.py", monkeypatch, prepend_stock_crawling=True)
    monkeypatch.setattr(module, "resolve_service_account_file", lambda explicit_path=None: "config/google_service_account.json")

    module.make_sheet_client()

    assert calls["credentials"][-1][0] == "config/google_service_account.json"



def test_env_example_documents_google_service_account_file() -> None:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "GOOGLE_SERVICE_ACCOUNT_FILE=config/google_service_account.json" in content
