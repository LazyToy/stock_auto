import tomllib
import importlib.util
from pathlib import Path


PYPROJECT_PATH = Path("pyproject.toml")



def _raw_dependencies() -> list[str]:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return data["project"]["dependencies"]



def _dependency_names() -> set[str]:
    dependencies = _raw_dependencies()
    names: set[str] = set()
    for entry in dependencies:
        normalized = entry.split(";", 1)[0].strip()
        for separator in ("<", ">", "=", "!", "~"):
            if separator in normalized:
                normalized = normalized.split(separator, 1)[0].strip()
                break
        if "[" in normalized:
            normalized = normalized.split("[", 1)[0].strip()
        names.add(normalized)
    return names



def test_pyproject_declares_core_crawling_runtime_dependencies() -> None:
    names = _dependency_names()

    assert {
        "beautifulsoup4",
        "finance-datareader",
        "google-auth",
        "gspread",
        "pandas",
    }.issubset(names)



def test_pyproject_uses_normalized_crawling_package_names() -> None:
    names = _dependency_names()
    raw_dependencies = _raw_dependencies()

    assert "bs4" not in names
    assert "google.oauth2.service_account" not in names
    assert "finance-datareader" in {name.lower() for name in names}
    assert not any(entry.startswith("FinanceDataReader") for entry in raw_dependencies)
    assert not any(entry.startswith("financedatareader") for entry in raw_dependencies)



def test_pyproject_keeps_crawling_readme_install_set_declared() -> None:
    names = _dependency_names()

    readme_runtime_set = {
        "gspread",
        "google-auth",
        "pandas",
        "beautifulsoup4",
        "finance-datareader",
    }

    assert readme_runtime_set.issubset(names)


def test_crawling_runtime_import_names_are_available() -> None:
    assert importlib.util.find_spec("FinanceDataReader") is not None
