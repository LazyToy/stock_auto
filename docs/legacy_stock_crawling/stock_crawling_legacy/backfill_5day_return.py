"""Backward-compatible shim for the migrated backfill_5day_return module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.backfill_5day_return")

is_backfill_ready = _module.is_backfill_ready
compute_5day_return = _module.compute_5day_return
_plus_bdays = _module._plus_bdays
backfill_early_signal_returns = _module.backfill_early_signal_returns
main = _module.main

__all__ = [
    "is_backfill_ready",
    "compute_5day_return",
    "_plus_bdays",
    "backfill_early_signal_returns",
    "main",
]
