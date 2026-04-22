"""Backward-compatible shim for the migrated telegram_notifier module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.telegram_notifier")

TelegramNotifier = _module.TelegramNotifier
should_notify_kr_surge = _module.should_notify_kr_surge
should_notify_theme_cluster = _module.should_notify_theme_cluster
format_surge_message = _module.format_surge_message
format_theme_message = _module.format_theme_message
format_error_message = _module.format_error_message
load_telegram_config = _module.load_telegram_config

__all__ = [
    "TelegramNotifier",
    "should_notify_kr_surge",
    "should_notify_theme_cluster",
    "format_surge_message",
    "format_theme_message",
    "format_error_message",
    "load_telegram_config",
]
