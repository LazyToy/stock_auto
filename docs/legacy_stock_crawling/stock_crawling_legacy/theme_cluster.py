"""Backward-compatible shim for the migrated theme_cluster module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.theme_cluster")

THRESHOLD_CHANGE = _module.THRESHOLD_CHANGE
MIN_TICKERS = _module.MIN_TICKERS
compute_intensity = _module.compute_intensity
build_theme_clusters = _module.build_theme_clusters
cluster_to_sheet_row = _module.cluster_to_sheet_row

__all__ = [
    "THRESHOLD_CHANGE",
    "MIN_TICKERS",
    "compute_intensity",
    "build_theme_clusters",
    "cluster_to_sheet_row",
]
