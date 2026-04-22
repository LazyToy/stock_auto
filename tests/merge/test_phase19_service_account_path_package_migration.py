import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "service_account_path.py"
    spec = importlib.util.spec_from_file_location("legacy_service_account_path", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_service_account_path_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.service_account_path")

    assert callable(module.resolve_service_account_file)
    assert hasattr(module, "ENV_VAR_NAME")



def test_src_crawling_service_account_path_preserves_resolution_logic(monkeypatch) -> None:
    module = importlib.import_module("src.crawling.service_account_path")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "config/google_service_account.json")

    resolved = module.resolve_service_account_file()

    assert resolved == str(ROOT / "config" / "google_service_account.json")


def test_src_crawling_service_account_path_resolves_from_project_root(monkeypatch) -> None:
    module = importlib.import_module("src.crawling.service_account_path")
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.setattr(module, "REPO_ROOT", ROOT)
    monkeypatch.setattr(
        module,
        "DEFAULT_SERVICE_ACCOUNT_FILE",
        ROOT / "config" / "google_service_account.json",
    )

    resolved = module.resolve_service_account_file("config/google_service_account.json")

    assert resolved == str(ROOT / "config" / "google_service_account.json")


def test_src_crawling_service_account_path_falls_back_to_crawling_config(
    monkeypatch, tmp_path
) -> None:
    module = importlib.import_module("src.crawling.service_account_path")
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        module,
        "DEFAULT_SERVICE_ACCOUNT_FILE",
        tmp_path / "config" / "google_service_account.json",
    )
    monkeypatch.setattr(
        module,
        "CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE",
        tmp_path / "crawling" / "config" / "google_service_account.json",
    )
    monkeypatch.setattr(
        module,
        "LEGACY_SERVICE_ACCOUNT_FILE",
        tmp_path / "stock_crawling" / "service_account.json",
    )
    (tmp_path / "crawling" / "config").mkdir(parents=True)
    (tmp_path / "crawling" / "config" / "google_service_account.json").write_text(
        "{}", encoding="utf-8"
    )

    resolved = module.resolve_service_account_file()

    assert resolved == str(tmp_path / "crawling" / "config" / "google_service_account.json")


def test_src_crawling_service_account_path_recovers_env_config_to_crawling_config(
    monkeypatch, tmp_path
) -> None:
    module = importlib.import_module("src.crawling.service_account_path")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        module,
        "CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE",
        tmp_path / "crawling" / "config" / "google_service_account.json",
    )
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "config/google_service_account.json")
    (tmp_path / "crawling" / "config").mkdir(parents=True)
    (tmp_path / "crawling" / "config" / "google_service_account.json").write_text(
        "{}", encoding="utf-8"
    )

    resolved = module.resolve_service_account_file()

    assert resolved == str(tmp_path / "crawling" / "config" / "google_service_account.json")



def test_legacy_service_account_path_shim_matches_new_module(monkeypatch) -> None:
    new_module = importlib.import_module("src.crawling.service_account_path")
    legacy_module = _load_legacy_module()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "config/google_service_account.json")

    assert legacy_module.resolve_service_account_file() == new_module.resolve_service_account_file()


def test_src_stock_scraper_google_client_uses_project_root_service_account(
    monkeypatch,
) -> None:
    module = importlib.import_module("src.crawling.stock_scraper")
    calls: list[str] = []

    class FakeCredentials:
        @staticmethod
        def from_service_account_file(path, scopes):
            calls.append(path)
            return object()

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "config/google_service_account.json")
    monkeypatch.setattr(module, "Credentials", FakeCredentials)
    monkeypatch.setattr(module.gspread, "authorize", lambda credentials: SimpleNamespace())

    module.get_gspread_client()

    assert calls == [str(ROOT / "config" / "google_service_account.json")]
