"""Backward-compatible shim for the migrated news_aggregator module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.news_aggregator")

DEFAULT_STOPWORDS_KR = _module.DEFAULT_STOPWORDS_KR
DEFAULT_STOPWORDS_EN = _module.DEFAULT_STOPWORDS_EN
extract_keywords = _module.extract_keywords
build_gemini_prompt = _module.build_gemini_prompt
summarize_narrative = _module.summarize_narrative

__all__ = [
    "DEFAULT_STOPWORDS_KR",
    "DEFAULT_STOPWORDS_EN",
    "extract_keywords",
    "build_gemini_prompt",
    "summarize_narrative",
]
