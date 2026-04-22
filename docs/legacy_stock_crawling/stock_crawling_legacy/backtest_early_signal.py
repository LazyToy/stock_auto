"""Backward-compatible shim for the migrated backtest_early_signal module."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.crawling.backtest_early_signal import *  # noqa: F401,F403
