"""
TDD test: gemini_client.

Hermetic — no live network calls. http_post is injected as a fake so tests
never touch googleapis.com. Uses tempfile for .env.local fixtures.

Run
---
    PYTHONIOENCODING=utf-8 ./stock_crawling/Scripts/python.exe test_gemini_client.py
"""
from __future__ import annotations

import sys
import tempfile
import os

from gemini_client import (
    load_api_key,
    load_api_keys,
    call_gemini,
    call_gemini_with_fallback,
    make_gemini_fn,
)

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Helper: write a temp .env file and return its path
# ---------------------------------------------------------------------------

def _write_env(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 1. load_api_key — double-quoted value
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY="my-secret-key"\n')
val = load_api_key(p)
check("load_api_key: double-quoted value", val == "my-secret-key", f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 2. load_api_key — unquoted value
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY=plain_key_123\n')
val = load_api_key(p)
check("load_api_key: unquoted value", val == "plain_key_123", f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 3. load_api_key — single-quoted value
# ---------------------------------------------------------------------------

p = _write_env("GEMINI_API_KEY='single_quoted'\n")
val = load_api_key(p)
check("load_api_key: single-quoted value", val == "single_quoted", f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 4. load_api_key — file not found → None
# ---------------------------------------------------------------------------

val = load_api_key("/nonexistent/path/.env.local")
check("load_api_key: missing file → None", val is None, f"got {val!r}")

# ---------------------------------------------------------------------------
# 5. load_api_key — key not present in file → None
# ---------------------------------------------------------------------------

p = _write_env('OTHER_KEY="something"\nANOTHER=value\n')
val = load_api_key(p)
check("load_api_key: key absent → None", val is None, f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 6. load_api_key — empty value → None
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY=\n')
val = load_api_key(p)
check("load_api_key: empty value → None", val is None, f"got {val!r}")
_cleanup(p)

# 6b. empty double-quoted value → None
p = _write_env('GEMINI_API_KEY=""\n')
val = load_api_key(p)
check("load_api_key: empty double-quoted value → None", val is None, f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 7. load_api_key — whitespace around value stripped
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY=  spaced_key  \n')
val = load_api_key(p)
check("load_api_key: whitespace around value stripped", val == "spaced_key", f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 8. load_api_key — comments and blank lines ignored
# ---------------------------------------------------------------------------

p = _write_env(
    "# This is a comment\n"
    "\n"
    "OTHER=foo\n"
    "# another comment\n"
    'GEMINI_API_KEY="found_it"\n'
    "\n"
)
val = load_api_key(p)
check("load_api_key: comments and blank lines ignored", val == "found_it", f"got {val!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 9. call_gemini — happy path
# ---------------------------------------------------------------------------

_CANONICAL_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [{"text": "요약 텍스트"}]
            }
        }
    ]
}


def fake_http_ok(url: str, body: dict) -> dict:
    return _CANONICAL_RESPONSE


result = call_gemini("테스트 프롬프트", api_key="test-key", http_post=fake_http_ok)
check("call_gemini: happy path returns text", result == "요약 텍스트", f"got {result!r}")

# ---------------------------------------------------------------------------
# 10. call_gemini — returned text is stripped of surrounding whitespace
# ---------------------------------------------------------------------------

_WHITESPACE_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [{"text": "  앞뒤 공백  "}]
            }
        }
    ]
}


def fake_http_ws(url: str, body: dict) -> dict:
    return _WHITESPACE_RESPONSE


result = call_gemini("prompt", api_key="key", http_post=fake_http_ws)
check("call_gemini: returned text is stripped", result == "앞뒤 공백", f"got {result!r}")

# ---------------------------------------------------------------------------
# 11. call_gemini — empty candidates list → RuntimeError
# ---------------------------------------------------------------------------

def fake_http_empty_candidates(url: str, body: dict) -> dict:
    return {"candidates": []}


raised = False
try:
    call_gemini("prompt", api_key="key", http_post=fake_http_empty_candidates)
except RuntimeError:
    raised = True
check("call_gemini: empty candidates → RuntimeError", raised)

# ---------------------------------------------------------------------------
# 12. call_gemini — response with top-level "error" key → RuntimeError
# ---------------------------------------------------------------------------

def fake_http_error(url: str, body: dict) -> dict:
    return {"error": {"code": 400, "message": "API key not valid."}}


raised = False
try:
    call_gemini("prompt", api_key="bad-key", http_post=fake_http_error)
except RuntimeError:
    raised = True
check("call_gemini: error key in response → RuntimeError", raised)

# ---------------------------------------------------------------------------
# 13. call_gemini — malformed response missing candidates key → RuntimeError
# ---------------------------------------------------------------------------

def fake_http_malformed(url: str, body: dict) -> dict:
    return {"something_else": "unexpected"}


raised = False
try:
    call_gemini("prompt", api_key="key", http_post=fake_http_malformed)
except RuntimeError:
    raised = True
check("call_gemini: missing candidates key → RuntimeError", raised)

# ---------------------------------------------------------------------------
# 14. call_gemini — http_post raises → RuntimeError propagated/wrapped
# ---------------------------------------------------------------------------

def fake_http_raises(url: str, body: dict) -> dict:
    raise OSError("connection refused")


raised = False
try:
    call_gemini("prompt", api_key="key", http_post=fake_http_raises)
except (RuntimeError, OSError, Exception):
    raised = True
check("call_gemini: http_post raises → exception propagated", raised)

# ---------------------------------------------------------------------------
# 15. make_gemini_fn — None key → returns None
# ---------------------------------------------------------------------------

fn = make_gemini_fn(None)
check("make_gemini_fn: None key → None", fn is None, f"got {fn!r}")

# ---------------------------------------------------------------------------
# 16. make_gemini_fn — empty string key → returns None
# ---------------------------------------------------------------------------

fn = make_gemini_fn("")
check("make_gemini_fn: empty string key → None", fn is None, f"got {fn!r}")

# ---------------------------------------------------------------------------
# 17. make_gemini_fn — valid key returns callable
# ---------------------------------------------------------------------------

fn = make_gemini_fn("valid-key")
check("make_gemini_fn: valid key returns callable", callable(fn), f"got {fn!r}")

# ---------------------------------------------------------------------------
# 18. make_gemini_fn — closure forwards to call_gemini via fake http_post
# ---------------------------------------------------------------------------

# We need to test that the closure produced by make_gemini_fn actually
# calls call_gemini with a real http_post behind the scenes.
# We patch by using the injectable path: make_gemini_fn doesn't expose
# http_post, so we test the integration by having a valid key and
# verifying the closure returns a string (it will fail the real network
# call, but the exception is swallowed → empty string).
# Better: test with a monkeypatched module-level _default_http_post.

import gemini_client as _gc

_original_http = getattr(_gc, "_default_http_post", None)

captured_calls: list[tuple[str, dict]] = []


def _fake_module_http(url: str, body: dict) -> dict:
    captured_calls.append((url, body))
    return _CANONICAL_RESPONSE


# Temporarily replace the module-level default
_gc._default_http_post = _fake_module_http  # type: ignore[attr-defined]

fn = make_gemini_fn("my-api-key")
assert fn is not None
res = fn("hello prompt")

# Restore
if _original_http is not None:
    _gc._default_http_post = _original_http

check("make_gemini_fn: closure forwards prompt to http_post", res == "요약 텍스트", f"got {res!r}")
check("make_gemini_fn: closure includes api_key in URL",
      len(captured_calls) == 1 and "my-api-key" in captured_calls[0][0],
      f"url={captured_calls[0][0] if captured_calls else 'none'}")

# ---------------------------------------------------------------------------
# 19. make_gemini_fn — closure swallows exception → returns ""
# ---------------------------------------------------------------------------

def _raising_http(url: str, body: dict) -> dict:
    raise RuntimeError("network failure")


_gc._default_http_post = _raising_http  # type: ignore[attr-defined]

fn2 = make_gemini_fn("any-key")
assert fn2 is not None
res2 = fn2("some prompt")

if _original_http is not None:
    _gc._default_http_post = _original_http

check("make_gemini_fn: closure swallows exception → returns ''", res2 == "", f"got {res2!r}")

# ---------------------------------------------------------------------------
# 20. load_api_keys -- base key only
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY=base_key\n')
keys = load_api_keys(p)
check("load_api_keys: base key only returns [base_key]", keys == ["base_key"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 21. load_api_keys -- base + numbered keys in order
# ---------------------------------------------------------------------------

p = _write_env(
    'GEMINI_API_KEY=key0\n'
    'GEMINI_API_KEY_2=key2\n'
    'GEMINI_API_KEY_3=key3\n'
)
keys = load_api_keys(p)
check("load_api_keys: base+numbered returns ordered list",
      keys == ["key0", "key2", "key3"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 22. load_api_keys -- numbered only (no base key)
# ---------------------------------------------------------------------------

p = _write_env(
    'GEMINI_API_KEY_2=second\n'
    'GEMINI_API_KEY_3=third\n'
)
keys = load_api_keys(p)
check("load_api_keys: numbered-only keeps numeric order",
      keys == ["second", "third"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 23. load_api_keys -- duplicate values de-duplicated
# ---------------------------------------------------------------------------

p = _write_env(
    'GEMINI_API_KEY=dup\n'
    'GEMINI_API_KEY_2=dup\n'
    'GEMINI_API_KEY_3=unique\n'
)
keys = load_api_keys(p)
check("load_api_keys: duplicate values removed",
      keys == ["dup", "unique"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 24. load_api_keys -- missing file returns []
# ---------------------------------------------------------------------------

keys = load_api_keys("/nonexistent/.env")
check("load_api_keys: missing file returns []", keys == [], f"got {keys!r}")

# ---------------------------------------------------------------------------
# 25. load_api_keys -- no Gemini keys in file returns []
# ---------------------------------------------------------------------------

p = _write_env('OTHER_KEY=something\n')
keys = load_api_keys(p)
check("load_api_keys: no gemini keys returns []", keys == [], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 26. call_gemini_with_fallback -- first key succeeds, second not tried
# ---------------------------------------------------------------------------

call_count: list[int] = [0]

def fake_http_count_calls(url: str, body: dict) -> dict:
    call_count[0] += 1
    return _CANONICAL_RESPONSE

result = call_gemini_with_fallback(
    "prompt",
    api_keys=["key1", "key2"],
    http_post=fake_http_count_calls,
)
check("call_gemini_with_fallback: first key success, returns text",
      result == "요약 텍스트", f"got {result!r}")
check("call_gemini_with_fallback: stops after first success (1 call)",
      call_count[0] == 1, f"call_count={call_count[0]}")

# ---------------------------------------------------------------------------
# 27. call_gemini_with_fallback -- first key fails, second succeeds
# ---------------------------------------------------------------------------

attempt: list[int] = [0]

def fake_http_fail_first(url: str, body: dict) -> dict:
    attempt[0] += 1
    if "key1" in url:
        return {"error": {"code": 429, "message": "quota exceeded"}}
    return _CANONICAL_RESPONSE

result = call_gemini_with_fallback(
    "prompt",
    api_keys=["key1", "key2"],
    http_post=fake_http_fail_first,
)
check("call_gemini_with_fallback: first fails, second key used",
      result == "요약 텍스트", f"got {result!r}")
check("call_gemini_with_fallback: tried both keys (2 calls)",
      attempt[0] == 2, f"attempt={attempt[0]}")

# ---------------------------------------------------------------------------
# 28. call_gemini_with_fallback -- all keys fail -> RuntimeError
# ---------------------------------------------------------------------------

def fake_http_always_error(url: str, body: dict) -> dict:
    return {"error": {"code": 400, "message": "bad key"}}

raised = False
try:
    call_gemini_with_fallback(
        "prompt",
        api_keys=["k1", "k2", "k3"],
        http_post=fake_http_always_error,
    )
except RuntimeError:
    raised = True
check("call_gemini_with_fallback: all keys fail -> RuntimeError", raised)

# ---------------------------------------------------------------------------
# 29. call_gemini_with_fallback -- empty key list -> RuntimeError
# ---------------------------------------------------------------------------

raised = False
try:
    call_gemini_with_fallback("prompt", api_keys=[], http_post=fake_http_ok)
except RuntimeError:
    raised = True
check("call_gemini_with_fallback: empty keys -> RuntimeError", raised)

# ---------------------------------------------------------------------------
# 30. make_gemini_fn -- accepts list of keys and falls back
# ---------------------------------------------------------------------------

attempt2: list[int] = [0]

def fake_http_list_fallback(url: str, body: dict) -> dict:
    attempt2[0] += 1
    if "first-key" in url:
        raise OSError("connection refused")
    return _CANONICAL_RESPONSE

_gc._default_http_post = fake_http_list_fallback  # type: ignore[attr-defined]

fn_multi = make_gemini_fn(["first-key", "second-key"])
assert fn_multi is not None
res_multi = fn_multi("hello")

if _original_http is not None:
    _gc._default_http_post = _original_http

check("make_gemini_fn: list of keys, falls back to second",
      res_multi == "요약 텍스트", f"got {res_multi!r}")
check("make_gemini_fn: list tried both keys (2 calls)",
      attempt2[0] == 2, f"attempt2={attempt2[0]}")

# ---------------------------------------------------------------------------
# 31. make_gemini_fn -- empty list -> None
# ---------------------------------------------------------------------------

fn_empty = make_gemini_fn([])
check("make_gemini_fn: empty list -> None", fn_empty is None, f"got {fn_empty!r}")

# ---------------------------------------------------------------------------
# 32. load_api_keys -- comma-separated values on one line
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY=key_a,key_b,key_c\n')
keys = load_api_keys(p)
check("load_api_keys: comma-separated on one line → 3 keys",
      keys == ["key_a", "key_b", "key_c"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 33. load_api_keys -- comma-separated + numbered keys merged in order
# ---------------------------------------------------------------------------

p = _write_env(
    'GEMINI_API_KEY=key_a,key_b\n'
    'GEMINI_API_KEY_2=key_c\n'
)
keys = load_api_keys(p)
check("load_api_keys: comma-separated base + numbered key → 3 keys in order",
      keys == ["key_a", "key_b", "key_c"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 34. load_api_keys -- comma-separated with spaces stripped
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY= key_a , key_b , key_c \n')
keys = load_api_keys(p)
check("load_api_keys: comma-separated values with spaces stripped",
      keys == ["key_a", "key_b", "key_c"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# 35. load_api_keys -- comma-separated deduplicates
# ---------------------------------------------------------------------------

p = _write_env('GEMINI_API_KEY=dup_key,dup_key,unique_key\n')
keys = load_api_keys(p)
check("load_api_keys: comma-separated duplicates removed",
      keys == ["dup_key", "unique_key"], f"got {keys!r}")
_cleanup(p)

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

passed = sum(1 for r in results if r)
total = len(results)
print()
print("=" * 60)
print(f"  RESULT: {passed}/{total} checks passed")
print("=" * 60)

sys.exit(0 if passed == total else 1)
