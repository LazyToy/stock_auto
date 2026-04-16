"""GeminiKeyManager 유닛 테스트 (TDD Red → Green → Refactor)

테스트 범위:
- GOOGLE_API_KEY=key1,key2,key3 쉼표 구분 방식
- 단일 키 로드 (하위 호환)
- 빈 키 / 공백 필터링
- fallback 순서 보장
- 모든 키 소진 시 예외 동작
- 키 sticky-current 기억
"""

import pytest
from unittest.mock import patch


# ─────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────
def make_manager(env_vars: dict):
    """환경변수를 주입해서 GeminiKeyManager 인스턴스 생성"""
    import sys
    with patch.dict("os.environ", env_vars, clear=True):
        mod_name = "src.utils.gemini_key_manager"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        from src.utils.gemini_key_manager import GeminiKeyManager
        return GeminiKeyManager()


# ─────────────────────────────────────────
# 1. 키 로드 테스트
# ─────────────────────────────────────────
class TestKeyLoading:
    """환경변수에서 API 키를 올바르게 로드하는지 검증"""

    def test_단일_키_로드(self):
        """GOOGLE_API_KEY 단일 키가 정상 로드되어야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "only_key"})
        keys = manager.get_all_keys()
        assert "only_key" in keys
        assert len(keys) == 1

    def test_쉼표_구분_다중_키_로드(self):
        """GOOGLE_API_KEY=key1,key2,key3 형태로 여러 키가 로드되어야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one,key_two,key_three"})
        keys = manager.get_all_keys()
        assert "key_one" in keys
        assert "key_two" in keys
        assert "key_three" in keys
        assert len(keys) == 3

    def test_쉼표_앞뒤_공백_제거(self):
        """키 앞뒤 공백이 trim되어야 한다 (key1, key2 → key1, key2)"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one , key_two , key_three"})
        keys = manager.get_all_keys()
        assert "key_one" in keys
        assert "key_two" in keys
        assert "key_three" in keys
        # 공백 포함 문자열이 없어야 함
        assert all(k == k.strip() for k in keys)

    def test_빈_세그먼트_필터링(self):
        """쉼표 연속(key1,,key2) 또는 빈 값은 제외되어야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one,,key_two,   ,"})
        keys = manager.get_all_keys()
        assert "key_one" in keys
        assert "key_two" in keys
        # 빈 값, 공백만 있는 세그먼트 없어야 함
        assert all(k.strip() != "" for k in keys)
        assert len(keys) == 2

    def test_중복_키_제거(self):
        """동일한 키가 중복으로 포함되면 한 번만 유지되어야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "key_a,key_b,key_a"})
        keys = manager.get_all_keys()
        assert keys.count("key_a") == 1
        assert len(keys) == 2

    def test_환경변수_없으면_빈_리스트(self):
        """키가 하나도 없으면 빈 리스트를 반환해야 한다"""
        manager = make_manager({})
        assert manager.get_all_keys() == []

    def test_키_개수_반환(self):
        """key_count()가 실제 유효 키 수를 반환해야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "k1,k2,k3"})
        assert manager.key_count() == 3

    def test_순서_보장(self):
        """쉼표 구분 키들이 입력 순서대로 로드되어야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "first,second,third"})
        keys = manager.get_all_keys()
        assert keys == ["first", "second", "third"]


# ─────────────────────────────────────────
# 2. get_available_key() - 현재 키 반환
# ─────────────────────────────────────────
class TestGetAvailableKey:
    """get_available_key()가 유효한 키를 올바르게 반환하는지 검증"""

    def test_단일_키_반환(self):
        """단일 키 환경에서 해당 키를 반환해야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "only_key"})
        assert manager.get_available_key() == "only_key"

    def test_키_없으면_None_반환(self):
        """유효한 키가 없으면 None을 반환해야 한다"""
        manager = make_manager({})
        assert manager.get_available_key() is None

    def test_다중_키_중_첫번째_반환(self):
        """다중 키 환경에서 첫 번째 키를 반환해야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "first_key,second_key"})
        assert manager.get_available_key() == "first_key"


# ─────────────────────────────────────────
# 3. fallback 로직
# ─────────────────────────────────────────
class TestFallback:
    """API 오류 발생 시 다음 키로 자동 fallback되는지 검증"""

    def test_첫번째_키_실패시_두번째로_fallback(self):
        """첫 번째 키에서 quota exceeded → 두 번째 키로 자동 전환"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one,key_two"})

        call_count = 0

        def mock_api_call(api_key: str):
            nonlocal call_count
            call_count += 1
            if api_key == "key_one":
                raise Exception("quota exceeded")
            return f"response_from_{api_key}"

        result = manager.call_with_fallback(mock_api_call)
        assert result == "response_from_key_two"
        assert call_count == 2

    def test_모든_키_실패시_예외_발생(self):
        """모든 키가 quota 초과면 GeminiKeyExhaustedError 발생"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one,key_two"})

        from src.utils.gemini_key_manager import GeminiKeyExhaustedError

        def always_fails(api_key: str):
            raise Exception("quota exceeded")

        with pytest.raises(GeminiKeyExhaustedError):
            manager.call_with_fallback(always_fails)

    def test_일반_예외는_fallback_안함(self):
        """quota 메시지 없는 예외는 즉시 재발생 (fallback 안 함)"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one,key_two"})

        def raises_value_error(api_key: str):
            raise ValueError("잘못된 요청")

        with pytest.raises(ValueError):
            manager.call_with_fallback(raises_value_error)

    def test_성공_키_인덱스_기억(self):
        """fallback 성공 후 다음 호출은 성공한 키부터 시작 (sticky current)"""
        manager = make_manager({"GOOGLE_API_KEY": "key_one,key_two"})

        attempts = []

        def mock_call_1(api_key: str):
            attempts.append(api_key)
            if api_key == "key_one":
                raise Exception("quota exceeded")
            return "ok"

        manager.call_with_fallback(mock_call_1)
        assert attempts[-1] == "key_two"

        # 두 번째 호출: key_two부터 시작해야 함
        attempts.clear()

        def mock_call_2(api_key: str):
            attempts.append(api_key)
            return "ok"

        manager.call_with_fallback(mock_call_2)
        assert attempts[0] == "key_two"

    def test_세_키_순서대로_fallback(self):
        """3개 키에서 순서대로 fallback되어야 한다"""
        manager = make_manager({"GOOGLE_API_KEY": "k1,k2,k3"})

        order = []

        def mock_call(api_key: str):
            order.append(api_key)
            if api_key in ("k1", "k2"):
                raise Exception("rate limit exceeded")
            return "ok_k3"

        result = manager.call_with_fallback(mock_call)
        assert result == "ok_k3"
        assert order == ["k1", "k2", "k3"]


# ─────────────────────────────────────────
# 4. Config 통합 테스트
# ─────────────────────────────────────────
class TestConfigIntegration:
    """Config.get_gemini_api_keys()가 쉼표 구분 키를 올바르게 반환하는지 검증"""

    def test_단일_키_리스트_반환(self):
        """단일 키도 리스트로 반환되어야 한다"""
        import sys
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "cfg_key"}, clear=True):
            for m in list(sys.modules.keys()):
                if "src.config" in m or "src.utils.gemini_key_manager" in m:
                    del sys.modules[m]
            from src.config import Config
            keys = Config.get_gemini_api_keys()
            assert isinstance(keys, list)
            assert "cfg_key" in keys

    def test_쉼표_구분_다중_키_반환(self):
        """쉼표 구분 키를 모두 반환해야 한다"""
        import sys
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "k1,k2,k3"}, clear=True):
            for m in list(sys.modules.keys()):
                if "src.config" in m or "src.utils.gemini_key_manager" in m:
                    del sys.modules[m]
            from src.config import Config
            keys = Config.get_gemini_api_keys()
            assert keys == ["k1", "k2", "k3"]
