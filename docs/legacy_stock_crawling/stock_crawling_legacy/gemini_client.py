"""Backward-compatible shim for the migrated gemini_client module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.gemini_client")

_GEMINI_ENDPOINT = _module._GEMINI_ENDPOINT
_default_http_post = _module._default_http_post

load_api_key = _module.load_api_key
load_api_keys = _module.load_api_keys


def call_gemini(
    prompt: str,
    *,
    api_key: str,
    http_post: Callable[[str, dict], dict] | None = None,
) -> str:
    return _module.call_gemini(prompt, api_key=api_key, http_post=http_post or _default_http_post)



def call_gemini_with_fallback(
    prompt: str,
    *,
    api_keys: list[str],
    http_post: Callable[[str, dict], dict] | None = None,
) -> str:
    return _module.call_gemini_with_fallback(prompt, api_keys=api_keys, http_post=http_post or _default_http_post)



def make_gemini_fn(api_key: str | list[str] | None):
    if not api_key:
        return None

    keys: list[str] = [api_key] if isinstance(api_key, str) else [k for k in api_key if k]
    if not keys:
        return None

    def _call(prompt: str) -> str:
        try:
            return call_gemini_with_fallback(prompt, api_keys=keys)
        except Exception:
            return ""

    return _call


__all__ = [
    "load_api_key",
    "load_api_keys",
    "call_gemini",
    "call_gemini_with_fallback",
    "make_gemini_fn",
    "_default_http_post",
]
