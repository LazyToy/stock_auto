"""Backward-compatible shim for the migrated generate_snapshots module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.generate_snapshots")

_last_iso_week = _module._last_iso_week
_build_ohlcv_rows = _module._build_ohlcv_rows
run_snapshots = _module.run_snapshots
main = _module.main

__all__ = ["_last_iso_week", "_build_ohlcv_rows", "run_snapshots", "main"]
