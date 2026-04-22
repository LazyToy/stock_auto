"""Backward-compatible shim for the migrated theme_trend module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.theme_trend")

aggregate_weekly = _module.aggregate_weekly
weekly_trend_to_sheet_row = _module.weekly_trend_to_sheet_row

__all__ = ["aggregate_weekly", "weekly_trend_to_sheet_row"]
