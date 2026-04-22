"""Backward-compatible shim for the migrated news_fetcher module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.news_fetcher")

fetch_kr_titles = _module.fetch_kr_titles
fetch_us_titles = _module.fetch_us_titles

__all__ = ["fetch_kr_titles", "fetch_us_titles"]
