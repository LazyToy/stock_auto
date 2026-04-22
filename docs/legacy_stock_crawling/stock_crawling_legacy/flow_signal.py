"""Backward-compatible shim for the migrated flow_signal module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.flow_signal")

FLOW_SIGNAL_HEADERS = _module.FLOW_SIGNAL_HEADERS
detect_reversal = _module.detect_reversal
build_flow_signal_row = _module.build_flow_signal_row

__all__ = ["FLOW_SIGNAL_HEADERS", "detect_reversal", "build_flow_signal_row"]
