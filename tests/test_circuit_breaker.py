"""CircuitBreaker 단위 테스트"""

import pytest
import time
from unittest.mock import MagicMock

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)


class TestCircuitBreakerCall:
    """CircuitBreaker.call() 메서드 테스트"""

    def test_call_success_in_closed_state(self):
        """CLOSED 상태에서 성공 호출"""
        cb = CircuitBreaker(name="test_closed_success")

        result = cb.call(lambda: 42)

        assert result == 42
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.total_successes == 1

    def test_call_passes_args_and_kwargs(self):
        """call()이 인자와 키워드 인자를 올바르게 전달하는지 확인"""
        cb = CircuitBreaker(name="test_args")

        def add(a, b, multiplier=1):
            return (a + b) * multiplier

        result = cb.call(add, 3, 4, multiplier=2)

        assert result == 14

    def test_call_records_failure_on_exception(self):
        """예외 발생 시 실패가 기록되는지 확인"""
        cb = CircuitBreaker(name="test_failure_record")

        def failing_func():
            raise ValueError("error")

        with pytest.raises(ValueError):
            cb.call(failing_func)

        assert cb.stats.total_failures == 1
        assert cb.stats.consecutive_failures == 1

    def test_call_opens_circuit_after_threshold(self):
        """실패 임계값 초과 시 서킷이 OPEN 상태로 전환되는지 확인"""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config=config, name="test_open_on_threshold")

        def failing_func():
            raise RuntimeError("fail")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

    def test_call_raises_circuit_breaker_error_when_open(self):
        """OPEN 상태에서 call() 호출 시 CircuitBreakerError 발생"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
        cb = CircuitBreaker(config=config, name="test_open_error")

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerError) as exc_info:
            cb.call(lambda: "should not reach here")

        assert exc_info.value.remaining_seconds > 0

    def test_call_transitions_to_half_open_after_timeout(self):
        """타임아웃 경과 후 HALF_OPEN 상태로 전환"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker(config=config, name="test_half_open")

        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        # timeout_seconds=0이므로 즉시 HALF_OPEN으로 전환
        assert cb.state == CircuitState.HALF_OPEN

    def test_call_closes_circuit_after_success_in_half_open(self):
        """HALF_OPEN 상태에서 성공 임계값 도달 시 CLOSED로 전환"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0,
            success_threshold=2,
        )
        cb = CircuitBreaker(config=config, name="test_close_from_half_open")

        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        # HALF_OPEN 진입 확인
        assert cb.state == CircuitState.HALF_OPEN

        cb.call(lambda: "ok")
        cb.call(lambda: "ok")

        assert cb.state == CircuitState.CLOSED

    def test_call_reopens_circuit_on_failure_in_half_open(self):
        """HALF_OPEN 상태에서 실패 시 다시 OPEN으로 전환"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker(config=config, name="test_reopen_from_half_open")

        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.HALF_OPEN

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail again")))

        assert cb.state == CircuitState.OPEN

    def test_decorator_usage(self):
        """데코레이터 방식으로 사용 시 정상 동작 확인"""
        cb = CircuitBreaker(name="test_decorator")

        @cb
        def my_func(x):
            return x * 2

        assert my_func(5) == 10
        assert cb.stats.total_successes == 1
