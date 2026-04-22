"""
gemini_client — Gemini REST API 클라이언트 (urllib 기반, 외부 SDK 미사용).

Public surface
--------------
* ``load_api_key(env_path)``
    dotenv 형식 파일에서 GEMINI_API_KEY 값을 파싱해 반환 (단일 키, 하위 호환).

* ``load_api_keys(env_path)``
    dotenv 형식 파일에서 GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3 ...
    를 순서대로 읽어 중복 제거 후 리스트로 반환.

* ``call_gemini(prompt, *, api_key, http_post)``
    Gemini generateContent REST 엔드포인트를 호출하고 생성된 텍스트를 반환.

* ``call_gemini_with_fallback(prompt, *, api_keys, http_post)``
    api_keys 목록을 순서대로 시도해 첫 성공 응답을 반환.
    모든 키 실패 시 RuntimeError raise.

* ``make_gemini_fn(api_key)``
    news_aggregator.summarize_narrative 의 gemini_fn 파라미터에 직접
    전달 가능한 클로저를 반환. api_key 가 str 이면 단일 키, list[str] 이면
    fallback 다중 키로 동작. None/빈값이면 None 반환.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-3.1-flash-lite:generateContent?key={api_key}"
)


# ---------------------------------------------------------------------------
# Module-level injectable HTTP backend (테스트에서 monkey-patch 가능)
# ---------------------------------------------------------------------------

def _default_http_post(url: str, body: dict) -> dict:
    """urllib 로 JSON POST 요청을 수행하고 파싱된 응답 dict 를 반환."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 1. load_api_key
# ---------------------------------------------------------------------------

def load_api_key(env_path: str = ".env.local") -> str | None:
    """
    dotenv 형식 파일에서 GEMINI_API_KEY 값을 파싱해 반환한다.

    - ``KEY="value"`` / ``KEY=value`` / ``KEY='value'`` 형식 지원
    - 주석(#) 및 빈 줄 무시
    - 파일 없음 / 키 없음 / 빈 값이면 None 반환
    """
    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        if key.strip() != "GEMINI_API_KEY":
            continue
        value = raw_value.strip()
        # 따옴표 제거 (쌍따옴표 또는 홑따옴표)
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
        return value if value else None

    return None


# ---------------------------------------------------------------------------
# 1b. load_api_keys
# ---------------------------------------------------------------------------

_GEMINI_KEY_RE = re.compile(r'^GEMINI_API_KEY(_\d+)?$')


def load_api_keys(env_path: str = ".env.local") -> list[str]:
    """
    dotenv 형식 파일에서 모든 Gemini API 키를 순서대로 로드한다.

    지원 형식::

        GEMINI_API_KEY=key0        # 기본 키 (첫 번째로 사용)
        GEMINI_API_KEY_2=key2
        GEMINI_API_KEY_3=key3

    - 중복된 값은 제거됨 (첫 등장 위치 유지)
    - 파일 없음 / 키 없음이면 빈 리스트 반환
    """
    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []

    raw: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        key = key.strip()
        if not _GEMINI_KEY_RE.match(key):
            continue
        value = raw_value.strip()
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
        if value:
            raw[key] = value

    ordered: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        """쉼표 구분 값을 분해해 중복 없이 ordered에 추가."""
        for part in value.split(","):
            v = part.strip()
            if v and v not in seen:
                ordered.append(v)
                seen.add(v)

    # 기본 키 먼저
    if "GEMINI_API_KEY" in raw:
        _add(raw["GEMINI_API_KEY"])

    # 번호 키를 숫자 순으로
    numbered = {k: v for k, v in raw.items() if k != "GEMINI_API_KEY"}
    for k in sorted(numbered, key=lambda x: int(x.rsplit("_", 1)[-1])):
        _add(numbered[k])

    return ordered


# ---------------------------------------------------------------------------
# 2. call_gemini
# ---------------------------------------------------------------------------

def call_gemini(
    prompt: str,
    *,
    api_key: str,
    http_post: Callable[[str, dict], dict] | None = None,
) -> str:
    """
    Gemini generateContent 엔드포인트를 호출하고 생성된 텍스트를 반환한다.

    Parameters
    ----------
    prompt:
        Gemini 에 전달할 텍스트 프롬프트.
    api_key:
        Gemini API 키.
    http_post:
        ``(url, body_dict) -> response_dict`` 형태의 injectable HTTP 함수.
        None 이면 모듈 수준 ``_default_http_post`` 를 사용한다.

    Raises
    ------
    RuntimeError
        HTTP 오류, JSON 파싱 오류, 응답에 candidates 누락/빈 경우,
        응답에 error 키가 있는 경우.
    """
    _post = http_post if http_post is not None else _default_http_post
    url = _GEMINI_ENDPOINT.format(api_key=api_key)
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    response = _post(url, body)

    if "error" in response:
        raise RuntimeError(f"Gemini API 오류: {response['error']}")

    if "candidates" not in response:
        raise RuntimeError(f"응답에 candidates 키 없음: {response!r}")

    candidates = response["candidates"]
    if not candidates:
        raise RuntimeError("candidates 목록이 비어 있음")

    try:
        text: str = candidates[0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"응답 구조 파싱 실패: {exc}") from exc

    return text.strip()


# ---------------------------------------------------------------------------
# 3. call_gemini_with_fallback
# ---------------------------------------------------------------------------

def call_gemini_with_fallback(
    prompt: str,
    *,
    api_keys: list[str],
    http_post: Callable[[str, dict], dict] | None = None,
) -> str:
    """
    api_keys 목록의 키를 순서대로 시도하며 첫 성공 응답을 반환한다.

    - 각 키에서 RuntimeError 가 발생하면 다음 키로 넘어간다.
    - 모든 키 실패 시 마지막 예외를 담은 RuntimeError 를 raise 한다.
    - api_keys 가 비어 있으면 즉시 RuntimeError.
    """
    if not api_keys:
        raise RuntimeError("api_keys 목록이 비어 있음")

    last_exc: Exception | None = None
    for key in api_keys:
        try:
            return call_gemini(prompt, api_key=key, http_post=http_post)
        except Exception as exc:
            last_exc = exc
            continue

    raise RuntimeError(
        f"모든 Gemini API 키 실패 (총 {len(api_keys)}개): {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# 4. make_gemini_fn
# ---------------------------------------------------------------------------

def make_gemini_fn(
    api_key: str | list[str] | None,
) -> Callable[[str], str] | None:
    """
    news_aggregator 의 gemini_fn 파라미터에 전달 가능한 클로저를 반환한다.

    api_key 동작:
    - None / 빈 문자열 / 빈 리스트 → None 반환
    - str → 단일 키로 call_gemini 호출
    - list[str] → call_gemini_with_fallback 으로 순서대로 시도

    클로저 내부 예외는 모두 삼켜지며 빈 문자열을 반환한다.
    (news_aggregator 는 빈 문자열을 fallback 신호로 취급한다.)
    """
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
