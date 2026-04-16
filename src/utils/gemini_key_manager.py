"""Gemini API 키 관리 모듈 — 다중 키 fallback 전략

환경변수 로드 순서:
1. GOOGLE_API_KEY_1, GOOGLE_API_KEY_2, ... (넘버드 방식 — 권장)
2. GOOGLE_API_KEY (레거시 단일 키 — 하위 호환)

중복 키는 자동으로 제거하며, 빈 문자열/공백만 있는 키는 무시합니다.

Fallback 전략:
- ResourceExhausted (할당량 초과) 오류 발생 시 다음 키로 자동 전환
- 성공한 키 인덱스를 기억하여 다음 호출 시 해당 키부터 시작 (sticky current)
- 모든 키 소진 시 GeminiKeyExhaustedError 발생

사용 예시:
    from src.utils.gemini_key_manager import GeminiKeyManager

    manager = GeminiKeyManager()

    def my_api_call(api_key: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        return model.generate_content("Hello")

    response = manager.call_with_fallback(my_api_call)
"""

import os
import logging
from typing import Callable, List, Optional, TypeVar

logger = logging.getLogger("GeminiKeyManager")

T = TypeVar("T")

# ResourceExhausted 예외 동적 임포트 (google-api-core 없는 환경 대비)
try:
    from google.api_core.exceptions import ResourceExhausted as _ResourceExhausted
    _RESOURCE_EXHAUSTED_CLASS: Optional[type] = _ResourceExhausted
except ImportError:
    _RESOURCE_EXHAUSTED_CLASS = None

# 할당량 초과를 나타내는 에러 메시지 패턴 (소문자 검사)
_QUOTA_ERROR_PATTERNS = [
    "quota",
    "resource_exhausted",
    "resourceexhausted",
    "429",
    "rate limit",
    "too many requests",
]


def _is_quota_error(exc: Exception) -> bool:
    """예외가 할당량 초과로 인한 것인지 판별.

    google.api_core.exceptions.ResourceExhausted 인스턴스이거나
    에러 메시지에 할당량 관련 패턴이 포함된 경우 True 반환.
    """
    if _RESOURCE_EXHAUSTED_CLASS is not None and isinstance(exc, _RESOURCE_EXHAUSTED_CLASS):
        return True
    msg = str(exc).lower()
    return any(pattern in msg for pattern in _QUOTA_ERROR_PATTERNS)


class GeminiKeyExhaustedError(Exception):
    """사용 가능한 Gemini API 키를 모두 소진했을 때 발생하는 예외"""
    pass


class GeminiKeyManager:
    """Gemini API 키 다중 관리 및 fallback 전략 클래스

    인스턴스 생성 시 환경변수를 스캔하여 사용 가능한 키 목록을 구성합니다.
    이후 call_with_fallback()을 통해 자동 키 전환 로직을 실행합니다.
    """

    def __init__(self):
        """환경변수에서 Gemini API 키 목록 로드 및 초기화"""
        self._keys: List[str] = self._load_keys()
        # 마지막으로 성공한 키의 인덱스 (sticky current 전략)
        self._current_index: int = 0

        if not self._keys:
            logger.warning(
                "사용 가능한 Gemini API 키가 없습니다. "
                ".env 파일에 GOOGLE_API_KEY 또는 GOOGLE_API_KEY_1 등을 설정하세요."
            )
        else:
            logger.info(f"Gemini API 키 {len(self._keys)}개 로드 완료")

    # ─────────────────────────────────────────
    # Public Interface
    # ─────────────────────────────────────────

    def get_all_keys(self) -> List[str]:
        """로드된 모든 유효 API 키 목록 반환 (읽기 전용 복사본)"""
        return list(self._keys)

    def key_count(self) -> int:
        """유효 API 키 수 반환"""
        return len(self._keys)

    def get_available_key(self) -> Optional[str]:
        """현재 사용 가능한 API 키 반환.

        Returns:
            str: 현재 키. 키가 없으면 None.
        """
        if not self._keys:
            return None
        return self._keys[self._current_index % len(self._keys)]

    def call_with_fallback(self, api_func: Callable[[str], T]) -> T:
        """API 함수를 실행하되, ResourceExhausted 발생 시 다음 키로 자동 전환.

        Args:
            api_func: api_key(str)를 인자로 받는 callable.
                      ResourceExhausted 예외를 발생시키면 다음 키로 fallback.

        Returns:
            api_func의 반환값

        Raises:
            GeminiKeyExhaustedError: 모든 키가 소진된 경우
            Exception: ResourceExhausted 이외의 예외는 즉시 재발생

        Example:
            def call_gemini(api_key: str):
                genai.configure(api_key=api_key)
                return genai.GenerativeModel("gemini-2.5-flash").generate_content("Hello")

            result = manager.call_with_fallback(call_gemini)
        """
        if not self._keys:
            raise GeminiKeyExhaustedError("사용 가능한 Gemini API 키가 없습니다.")

        n = len(self._keys)

        for attempt in range(n):
            # sticky current 전략: 마지막 성공 인덱스부터 순환
            idx = (self._current_index + attempt) % n
            key = self._keys[idx]

            try:
                result = api_func(key)
                # 성공 → 현재 인덱스 갱신
                self._current_index = idx
                if attempt > 0:
                    logger.info(f"키 인덱스 {idx}로 fallback 성공 (시도 횟수: {attempt + 1})")
                return result

            except Exception as exc:
                if _is_quota_error(exc):
                    logger.warning(
                        f"키[{idx}] 할당량 초과: {exc}. "
                        f"다음 키로 전환 ({attempt + 1}/{n})"
                    )
                    continue
                # 할당량 이외 예외는 즉시 재발생 (fallback 안 함)
                raise

        # 모든 키 소진
        raise GeminiKeyExhaustedError(
            f"모든 Gemini API 키({n}개)가 할당량을 초과했습니다. "
            "잠시 후 다시 시도하거나 새로운 키를 추가하세요."
        )

    # ─────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _load_keys() -> List[str]:
        """환경변수에서 Gemini API 키 목록 로드.

        GOOGLE_API_KEY 환경변수에 쉼표(,)로 구분하여 여러 키를 지정할 수 있습니다.

        예시:
            # 단일 키
            GOOGLE_API_KEY=AIzaSy...abc

            # 다중 키 (쉼표 구분)
            GOOGLE_API_KEY=AIzaSy...abc,AIzaSy...def,AIzaSy...ghi

        처리 규칙:
        - 각 키의 앞뒤 공백 자동 제거 (strip)
        - 빈 문자열/공백만 있는 세그먼트 제외
        - 중복 키 자동 제거 (첫 번째 등장 순서 유지)
        """
        raw = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not raw:
            return []

        keys: List[str] = []
        seen: set = set()

        for segment in raw.split(","):
            key = segment.strip()
            if key and key not in seen:
                keys.append(key)
                seen.add(key)

        return keys


# ─────────────────────────────────────────
# 전역 싱글톤 인스턴스
# (모듈 로드 시 한 번만 생성 — 환경변수 기반)
# ─────────────────────────────────────────
_global_manager: Optional[GeminiKeyManager] = None


def get_key_manager() -> GeminiKeyManager:
    """전역 GeminiKeyManager 싱글톤 반환.

    최초 호출 시 인스턴스 생성. 이후에는 동일 인스턴스 재사용.
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = GeminiKeyManager()
    return _global_manager
