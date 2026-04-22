"""Backward-compatible shim for the migrated sector_map_kr module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.sector_map_kr")

UNKNOWN_SECTOR = _module.UNKNOWN_SECTOR
CACHE_MAX_AGE_DAYS = _module.CACHE_MAX_AGE_DAYS
MIN_COVERAGE = _module.MIN_COVERAGE
SectorMapKR = _module.SectorMapKR
default_fetcher = _module.default_fetcher
_fetch_naver = _module._fetch_naver

__all__ = [
    "UNKNOWN_SECTOR",
    "CACHE_MAX_AGE_DAYS",
    "MIN_COVERAGE",
    "SectorMapKR",
    "default_fetcher",
    "_fetch_naver",
]
