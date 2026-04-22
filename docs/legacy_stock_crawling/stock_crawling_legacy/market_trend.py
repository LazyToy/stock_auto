"""Backward-compatible shim for the migrated market_trend module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.market_trend")

CheckResult = _module.CheckResult
Report = _module.Report
REQUIRED_KR_COLS = _module.REQUIRED_KR_COLS
PASS = _module.PASS
FAIL = _module.FAIL
INFO = _module.INFO
fetch_kr = _module.fetch_kr
kr_pipeline_checks = _module.kr_pipeline_checks
kr_trend_snapshot = _module.kr_trend_snapshot
fetch_us = _module.fetch_us
us_pipeline_checks = _module.us_pipeline_checks
us_trend_snapshot = _module.us_trend_snapshot

__all__ = [
    "CheckResult",
    "Report",
    "REQUIRED_KR_COLS",
    "PASS",
    "FAIL",
    "INFO",
    "fetch_kr",
    "kr_pipeline_checks",
    "kr_trend_snapshot",
    "fetch_us",
    "us_pipeline_checks",
    "us_trend_snapshot",
]
