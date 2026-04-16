from pathlib import Path
from dashboard.log_utils import ACTIVE_LOG_DIR_NAME, LEGACY_LOG_DIR_NAME, resolve_dashboard_log_path


def test_dashboard_reads_logs_from_active_logs_directory(tmp_path):
    resolved = resolve_dashboard_log_path("KR", base_dir=tmp_path)

    assert resolved == tmp_path / "logs" / ACTIVE_LOG_DIR_NAME / "auto_trader.log"


def test_dashboard_log_policy_exposes_legacy_directory_name():
    assert LEGACY_LOG_DIR_NAME == "legacy"


def test_logs_root_only_contains_policy_directories():
    entries = {entry.name for entry in Path("logs").iterdir()}

    assert "active" in entries
    assert "legacy" in entries
    assert "audit.jsonl" not in entries


def test_logger_default_uses_active_log_dir_constant():
    text = Path("src/utils/logger.py").read_text(encoding="utf-8")

    assert 'log_dir: str = "logs/active"' in text or 'ACTIVE_LOG_DIR_NAME' in text
