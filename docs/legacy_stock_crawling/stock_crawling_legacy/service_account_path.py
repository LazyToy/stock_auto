"""Backward-compatible shim for the migrated service_account_path module."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional at import time
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.service_account_path")

ENV_VAR_NAME = _module.ENV_VAR_NAME
REPO_ROOT = _module.REPO_ROOT
DEFAULT_SERVICE_ACCOUNT_FILE = _module.DEFAULT_SERVICE_ACCOUNT_FILE
CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE = _module.CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE
LEGACY_SERVICE_ACCOUNT_FILE = _module.LEGACY_SERVICE_ACCOUNT_FILE


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

__all__ = [
    "ENV_VAR_NAME",
    "REPO_ROOT",
    "DEFAULT_SERVICE_ACCOUNT_FILE",
    "CRAWLING_CONFIG_SERVICE_ACCOUNT_FILE",
    "LEGACY_SERVICE_ACCOUNT_FILE",
    "load_dotenv",
    "resolve_service_account_file",
]
