"""Shared logging configuration helpers for runtime scripts."""

import logging
from pathlib import Path

LOG_ROOT_DIR_NAME = "logs"
ACTIVE_LOG_DIR_NAME = "active"
LEGACY_LOG_DIR_NAME = "legacy"


def resolve_active_log_dir(*, base_dir: str | Path | None = None) -> Path:
    base_path = Path(base_dir) if base_dir is not None else Path.cwd()
    log_path = base_path / LOG_ROOT_DIR_NAME / ACTIVE_LOG_DIR_NAME
    log_path.mkdir(parents=True, exist_ok=True)
    return log_path


def resolve_legacy_log_dir(*, base_dir: str | Path | None = None) -> Path:
    base_path = Path(base_dir) if base_dir is not None else Path.cwd()
    legacy_path = base_path / LOG_ROOT_DIR_NAME / LEGACY_LOG_DIR_NAME
    legacy_path.mkdir(parents=True, exist_ok=True)
    return legacy_path


def resolve_log_file(file_name: str, *, base_dir: str | Path | None = None) -> str:
    return str(resolve_active_log_dir(base_dir=base_dir) / file_name)


def configure_script_logging(
    *,
    file_name: str,
    fmt: str,
    configured: bool = False,
    level: int = logging.INFO,
) -> bool:
    """Configure simple stream+file logging for runtime scripts."""
    if configured:
        return True

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.insert(0, logging.FileHandler(resolve_log_file(file_name), encoding="utf-8"))
    except OSError as exc:
        logging.getLogger().warning(f"{file_name} file handler disabled: {exc}")

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=handlers,
    )
    return True
