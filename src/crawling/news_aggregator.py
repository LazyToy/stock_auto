"""
news_aggregator — term-frequency keyword extraction + Gemini narrative.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable, Iterable

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)

DEFAULT_STOPWORDS_KR: frozenset[str] = frozenset({
    "의", "은", "는", "이", "가", "을", "를", "에", "와", "과",
    "도", "로", "으로", "만", "에서", "부터", "까지", "라고", "하고",
    "그리고", "또", "또한", "하지만", "그러나", "그래서", "따라서",
    "위해", "통해", "대한", "대해", "위한",
    "오늘", "어제", "내일", "현재", "지금", "최근", "이번", "지난",
    "매우", "아주", "정말", "더욱", "가장", "계속", "여전히",
    "관련", "관련해", "관련하여", "대비", "대비해", "대상",
    "기준", "이상", "이하", "중", "등", "및", "또는",
})

DEFAULT_STOPWORDS_EN: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at",
    "to", "for", "from", "by", "with", "as", "is", "are", "was",
    "were", "be", "been", "being", "has", "have", "had", "do", "does",
    "did", "will", "would", "can", "could", "should", "may", "might",
    "it", "its", "this", "that", "these", "those", "he", "she",
    "they", "them", "his", "her", "their", "we", "us", "our",
    "you", "your", "i", "me", "my", "not", "no", "so", "up", "down",
    "after", "before", "over", "under", "into", "than", "then",
    "here", "there", "when", "where", "what", "which", "who", "why",
    "how", "all", "any", "some", "one", "two", "new", "old",
    "amid", "vs",
})

_DEFAULT_STOPWORDS: frozenset[str] = DEFAULT_STOPWORDS_KR | DEFAULT_STOPWORDS_EN


def _tokenize(title: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RE.findall(title):
        tok = raw.lower() if raw.isascii() else raw
        out.append(tok)
    return out


def extract_keywords(
    titles: Iterable[str],
    *,
    stopwords: Iterable[str] | None = None,
    top_n: int = 10,
) -> list[tuple[str, int]]:
    sw: set[str] = set(stopwords) if stopwords is not None else set(_DEFAULT_STOPWORDS)
    counter: Counter[str] = Counter()

    for title in titles:
        if not title or not title.strip():
            continue
        for tok in _tokenize(title):
            if len(tok) < 2 or tok.isdigit() or tok in sw:
                continue
            counter[tok] += 1

    if not counter:
        return []

    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return items[:top_n]


def build_gemini_prompt(
    kr_keywords: list[tuple[str, int]],
    us_keywords: list[tuple[str, int]],
) -> str:
    kr_line = ", ".join(f"{tok}({cnt})" for tok, cnt in kr_keywords) or "(없음)"
    us_line = ", ".join(f"{tok}({cnt})" for tok, cnt in us_keywords) or "(없음)"
    return (
        "다음은 오늘의 한국과 미국 주식 뉴스 제목에서 추출한 상위 키워드입니다.\n"
        f"- 한국: {kr_line}\n"
        f"- 미국: {us_line}\n\n"
        "두 시장의 오늘 흐름을 한국어로 2~3문장 이내로 요약해주세요. "
        "추측이 아닌 키워드가 시사하는 바에 집중하세요."
    )


def _fallback_narrative(
    kr_keywords: list[tuple[str, int]],
    us_keywords: list[tuple[str, int]],
) -> str:
    kr = ", ".join(tok for tok, _ in kr_keywords[:5]) or "특이사항 없음"
    us = ", ".join(tok for tok, _ in us_keywords[:5]) or "특이사항 없음"
    return f"[AI 요약 미사용] 오늘 한국 시장 키워드: {kr}. 미국 시장 키워드: {us}."


def summarize_narrative(
    kr_keywords: list[tuple[str, int]],
    us_keywords: list[tuple[str, int]],
    *,
    gemini_fn: Callable[[str], str] | None,
) -> str:
    if gemini_fn is not None:
        try:
            prompt = build_gemini_prompt(kr_keywords, us_keywords)
            raw = gemini_fn(prompt)
        except Exception:
            raw = ""
        if raw and raw.strip():
            return raw.strip()
    return _fallback_narrative(kr_keywords, us_keywords)
