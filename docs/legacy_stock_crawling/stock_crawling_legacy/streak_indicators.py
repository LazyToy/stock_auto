"""Backward-compatible shim for the migrated streak_indicators module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.streak_indicators")

LOOKBACK_52W = _module.LOOKBACK_52W
ATR_PERIOD = _module.ATR_PERIOD
is_52w_high = _module.is_52w_high
is_52w_low = _module.is_52w_low
current_streak = _module.current_streak
atr14 = _module.atr14
compute_indicators = _module.compute_indicators

__all__ = [
    "LOOKBACK_52W",
    "ATR_PERIOD",
    "is_52w_high",
    "is_52w_low",
    "current_streak",
    "atr14",
    "compute_indicators",
]
