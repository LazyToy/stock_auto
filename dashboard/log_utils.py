from pathlib import Path

from src.utils.runtime_logging import ACTIVE_LOG_DIR_NAME, LEGACY_LOG_DIR_NAME, LOG_ROOT_DIR_NAME


def resolve_dashboard_log_path(market: str = "KR", base_dir: str | Path | None = None) -> Path:
    file_name = "us_trading.log" if market == "US" else "auto_trader.log"
    base_path = Path(base_dir) if base_dir is not None else Path.cwd()
    return base_path / LOG_ROOT_DIR_NAME / ACTIVE_LOG_DIR_NAME / file_name
