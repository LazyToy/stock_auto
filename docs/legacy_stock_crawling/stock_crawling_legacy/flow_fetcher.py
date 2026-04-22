"""Backward-compatible shim for the migrated flow_fetcher module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.flow_fetcher")

parse_foreign_institutional_flow = _module.parse_foreign_institutional_flow
fetch_flow = _module.fetch_flow
fetch_flow_batch = _module.fetch_flow_batch

__all__ = ["parse_foreign_institutional_flow", "fetch_flow", "fetch_flow_batch"]
