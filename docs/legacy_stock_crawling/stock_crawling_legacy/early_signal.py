"""Backward-compatible shim for the migrated early_signal module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.early_signal")

EARLY_SIGNAL_HEADERS = _module.EARLY_SIGNAL_HEADERS
is_early_signal = _module.is_early_signal
build_early_signal_row = _module.build_early_signal_row

__all__ = ["EARLY_SIGNAL_HEADERS", "is_early_signal", "build_early_signal_row"]
