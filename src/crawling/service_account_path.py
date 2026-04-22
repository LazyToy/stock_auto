from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional at import time
    load_dotenv = None

ENV_VAR_NAME = "GOOGLE_SERVICE_ACCOUNT_FILE"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVICE_ACCOUNT_FILE = REPO_ROOT / "config" / "google_service_account.json"
CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE = (
    REPO_ROOT / "crawling" / "config" / "google_service_account.json"
)
LEGACY_SERVICE_ACCOUNT_FILE = REPO_ROOT / "stock_crawling" / "service_account.json"



def _resolve_candidate(path_value: str) -> str:
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    resolved = REPO_ROOT / path
    if resolved.exists():
        return str(resolved)
    if path.as_posix() == "config/google_service_account.json":
        if CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE.exists():
            return str(CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE)
    return str(resolved)



def resolve_service_account_file(explicit_path: str | None = None) -> str:
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env", override=False)

    if explicit_path:
        return _resolve_candidate(explicit_path)

    env_path = os.getenv(ENV_VAR_NAME)
    if env_path:
        return _resolve_candidate(env_path)

    if DEFAULT_SERVICE_ACCOUNT_FILE.exists():
        return str(DEFAULT_SERVICE_ACCOUNT_FILE)

    if CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE.exists():
        return str(CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE)

    if LEGACY_SERVICE_ACCOUNT_FILE.exists():
        return str(LEGACY_SERVICE_ACCOUNT_FILE)

    return str(DEFAULT_SERVICE_ACCOUNT_FILE)
