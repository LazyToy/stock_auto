from pathlib import Path

from src.utils.runtime_logging import ACTIVE_LOG_DIR_NAME, LEGACY_LOG_DIR_NAME, resolve_log_file, resolve_legacy_log_dir


def test_resolve_log_file_places_logs_under_active_logs_dir(tmp_path):
    resolved = Path(resolve_log_file("auto_trader.log", base_dir=tmp_path))

    assert resolved == tmp_path / "logs" / ACTIVE_LOG_DIR_NAME / "auto_trader.log"
    assert resolved.parent.exists()


def test_resolve_legacy_log_dir_places_archives_under_legacy_dir(tmp_path):
    resolved = resolve_legacy_log_dir(base_dir=tmp_path)

    assert resolved == tmp_path / "logs" / LEGACY_LOG_DIR_NAME
    assert resolved.exists()
