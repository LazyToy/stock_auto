from pathlib import Path


def _gitignore_entries() -> set[str]:
    lines = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_gitignore_covers_stock_crawling_generated_artifacts() -> None:
    entries = _gitignore_entries()
    assert {
        "stock_crawling/.git/",
        "stock_crawling/stock_crawling/",
        "stock_crawling/node_modules/",
        "stock_crawling/dist/",
    }.issubset(entries)


def test_gitignore_covers_nested_secret_like_files() -> None:
    entries = _gitignore_entries()
    assert {
        "stock_crawling/.env*",
        "stock_crawling/service_account*.json",
    }.issubset(entries)


def test_gitignore_covers_root_secret_targets_for_future_relocation() -> None:
    entries = _gitignore_entries()
    assert {
        "service_account*.json",
        "config/google_service_account.json",
        "secrets/",
    }.issubset(entries)
