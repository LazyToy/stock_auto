"""Backward-compatible shim for the migrated daily_trend_writer module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.daily_trend_writer")

resolve_service_account_file = _module.resolve_service_account_file
NEWS_TAB = _module.NEWS_TAB
NEWS_HEADERS = _module.NEWS_HEADERS
KR_HEADERS = _module.KR_HEADERS
US_HEADERS = _module.US_HEADERS
EARLY_SIGNAL_TAB = _module.EARLY_SIGNAL_TAB
EARLY_SIGNAL_HEADERS = _module.EARLY_SIGNAL_HEADERS
format_keywords = _module.format_keywords
kr_snapshot_to_row = _module.kr_snapshot_to_row
us_snapshot_to_row = _module.us_snapshot_to_row
DailyTrendSheet = _module.DailyTrendSheet
THEME_CLUSTER_HEADERS = _module.THEME_CLUSTER_HEADERS
THEME_CLUSTER_TAB = _module.THEME_CLUSTER_TAB
MarketFlowSheet = _module.MarketFlowSheet


def make_sheet_client(service_account_file=None):
    _module.resolve_service_account_file = resolve_service_account_file
    return _module.make_sheet_client(service_account_file)

__all__ = [
    "NEWS_TAB",
    "resolve_service_account_file",
    "NEWS_HEADERS",
    "KR_HEADERS",
    "US_HEADERS",
    "EARLY_SIGNAL_TAB",
    "EARLY_SIGNAL_HEADERS",
    "format_keywords",
    "kr_snapshot_to_row",
    "us_snapshot_to_row",
    "DailyTrendSheet",
    "make_sheet_client",
    "THEME_CLUSTER_HEADERS",
    "THEME_CLUSTER_TAB",
    "MarketFlowSheet",
]
