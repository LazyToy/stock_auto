"""
TDD test: news_aggregator.

Hermetic — no live Gemini, no network. Fake Gemini callable is injected so
the unit test can pin narrative behavior in all three branches
(success / None / exception).

Run
---
    PYTHONIOENCODING=utf-8 ./stock_crawling/Scripts/python.exe test_news_aggregator.py
"""
from __future__ import annotations

import sys

from news_aggregator import (
    DEFAULT_STOPWORDS_EN,
    DEFAULT_STOPWORDS_KR,
    build_gemini_prompt,
    extract_keywords,
    summarize_narrative,
)

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# 1. extract_keywords — Korean news titles
# ---------------------------------------------------------------------------

kr_titles = [
    "삼성전자 반도체 실적 호조에 외국인 매수 쇄도",
    "SK하이닉스 HBM 수요 급증, 반도체 업황 회복 신호",
    "반도체 대장주 강세, 코스피 2700 돌파",
    "외국인 순매수 지속, 반도체 중심 랠리",
]

kr_kw = extract_keywords(kr_titles, top_n=5)
check("extract_keywords returns a list", isinstance(kr_kw, list))
check("extract_keywords items are (token, count) tuples",
      all(isinstance(t, tuple) and len(t) == 2 for t in kr_kw))
check("top KR keyword is '반도체'", kr_kw and kr_kw[0][0] == "반도체",
      f"got {kr_kw[0] if kr_kw else None}")
check("'반도체' count is 4", kr_kw and kr_kw[0][1] == 4)
check("'외국인' appears at least once",
      any(tok == "외국인" for tok, _ in kr_kw))
check("top_n respected", len(kr_kw) <= 5)

# ---------------------------------------------------------------------------
# 2. extract_keywords — English news titles (case-insensitive)
# ---------------------------------------------------------------------------

us_titles = [
    "Nvidia surges on strong AI demand, chip stocks rally",
    "AI chip demand boosts Nvidia and AMD",
    "Tesla drops after earnings miss, EV stocks slide",
    "Nvidia leads chip sector rally",
]

us_kw = extract_keywords(us_titles, top_n=5)
check("US extract returns entries", len(us_kw) > 0)

tokens_us = [tok for tok, _ in us_kw]
check("'nvidia' in US top-5 (case-folded)", "nvidia" in tokens_us,
      f"got {tokens_us}")
check("'chip' in US top-5", "chip" in tokens_us)

# ---------------------------------------------------------------------------
# 3. Stopwords are removed
# ---------------------------------------------------------------------------

stopword_kr_titles = [
    "오늘 의 시장 은 매우 의 외국인 매수",
    "그리고 또 의 매수 의 증가",
]
kw = extract_keywords(stopword_kr_titles, top_n=10)
toks = [t for t, _ in kw]
check("KR stopword '의' excluded", "의" not in toks, f"got {toks}")
check("KR stopword '오늘' excluded",
      "오늘" not in toks or "오늘" in DEFAULT_STOPWORDS_KR)

stopword_en_titles = ["The and the of the"]
kw_en = extract_keywords(stopword_en_titles, top_n=10)
check("EN stopword 'the' excluded",
      all(t != "the" for t, _ in kw_en),
      f"got {[t for t, _ in kw_en]}")

# ---------------------------------------------------------------------------
# 4. extract_keywords — edge cases
# ---------------------------------------------------------------------------

check("empty input → empty list", extract_keywords([], top_n=5) == [])
check("all-empty titles → empty list",
      extract_keywords(["", "   ", ""], top_n=5) == [])
check("numeric-only tokens filtered",
      all(not t.isdigit() for t, _ in extract_keywords(
          ["2700 돌파 2700 2700 코스피"], top_n=5)))
check("single-char tokens filtered",
      all(len(t) >= 2 for t, _ in extract_keywords(
          ["a 의 test test"], top_n=5)))

# ---------------------------------------------------------------------------
# 5. build_gemini_prompt — contains both sides
# ---------------------------------------------------------------------------

prompt = build_gemini_prompt(
    kr_keywords=[("반도체", 4), ("외국인", 2)],
    us_keywords=[("nvidia", 3), ("chip", 2)],
)
check("prompt is a str", isinstance(prompt, str))
check("prompt contains KR keyword '반도체'", "반도체" in prompt)
check("prompt contains US keyword 'nvidia'", "nvidia" in prompt)
check("prompt has explicit request for Korean output",
      "한국어" in prompt or "한글" in prompt)

# ---------------------------------------------------------------------------
# 6. summarize_narrative — gemini returns text
# ---------------------------------------------------------------------------

calls: list[str] = []


def fake_ok(p: str) -> str:
    calls.append(p)
    return "  AI반도체 랠리가 양국 증시를 주도했다.  "


narrative = summarize_narrative(
    kr_keywords=[("반도체", 4)],
    us_keywords=[("nvidia", 3)],
    gemini_fn=fake_ok,
)
check("narrative strips whitespace",
      narrative == "AI반도체 랠리가 양국 증시를 주도했다.",
      f"got {narrative!r}")
check("gemini_fn was called once with a prompt", len(calls) == 1)

# ---------------------------------------------------------------------------
# 7. summarize_narrative — gemini raises → fallback template
# ---------------------------------------------------------------------------

def fake_raise(p: str) -> str:
    raise RuntimeError("api down")


fb_narrative = summarize_narrative(
    kr_keywords=[("반도체", 4), ("외국인", 2)],
    us_keywords=[("nvidia", 3)],
    gemini_fn=fake_raise,
)
check("fallback returns a str", isinstance(fb_narrative, str))
check("fallback narrative is non-empty", len(fb_narrative) > 0)
check("fallback includes KR top keyword", "반도체" in fb_narrative)
check("fallback includes US top keyword", "nvidia" in fb_narrative)

# ---------------------------------------------------------------------------
# 8. summarize_narrative — gemini returns empty string → fallback
# ---------------------------------------------------------------------------

def fake_empty(p: str) -> str:
    return "   "


emp_narrative = summarize_narrative(
    kr_keywords=[("반도체", 4)],
    us_keywords=[("nvidia", 3)],
    gemini_fn=fake_empty,
)
check("empty gemini response → fallback (non-empty)",
      len(emp_narrative.strip()) > 0)
check("empty gemini response → fallback mentions keywords",
      "반도체" in emp_narrative and "nvidia" in emp_narrative)

# ---------------------------------------------------------------------------
# 9. summarize_narrative — gemini_fn is None → fallback
# ---------------------------------------------------------------------------

none_narrative = summarize_narrative(
    kr_keywords=[("반도체", 4)],
    us_keywords=[("nvidia", 3)],
    gemini_fn=None,
)
check("gemini_fn=None → fallback", "반도체" in none_narrative)

# ---------------------------------------------------------------------------
# 10. summarize_narrative — both sides empty → fallback template still works
# ---------------------------------------------------------------------------

empty_sides = summarize_narrative(
    kr_keywords=[],
    us_keywords=[],
    gemini_fn=None,
)
check("no keywords on either side → fallback is still a str",
      isinstance(empty_sides, str) and len(empty_sides) > 0)

# ---------------------------------------------------------------------------
# 11. Stopword constants
# ---------------------------------------------------------------------------

check("DEFAULT_STOPWORDS_KR is a set/frozenset",
      isinstance(DEFAULT_STOPWORDS_KR, (set, frozenset)))
check("DEFAULT_STOPWORDS_EN is a set/frozenset",
      isinstance(DEFAULT_STOPWORDS_EN, (set, frozenset)))
check("'의' is in KR stopwords", "의" in DEFAULT_STOPWORDS_KR)
check("'the' is in EN stopwords", "the" in DEFAULT_STOPWORDS_EN)

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
