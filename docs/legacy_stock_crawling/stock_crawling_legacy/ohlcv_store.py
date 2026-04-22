"""Backward-compatible shim for the migrated ohlcv_store module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.ohlcv_store")

OHLCVStore = _module.OHLCVStore
compute_avg_volume = _module.compute_avg_volume

__all__ = ["OHLCVStore", "compute_avg_volume"]
