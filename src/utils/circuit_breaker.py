"""Circuit Breaker 패턴

API 호출 실패 시 자동으로 서킷을 열어 연속 실패를 방지합니다.
서킷이 열리면 일정 시간 동안 새로운 요청을 차단합니다.

주요 기능:
- 연속 실패 횟수 추적
- 서킷 상태 관리 (CLOSED, OPEN, HALF_OPEN)
- 자동 복구 시도
- 텔레그램 알림 연동
"""

import time
import logging
import functools
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional, Any, Dict
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """서킷 상태"""
    CLOSED = "closed"       # 정상 상태 - 요청 허용
    OPEN = "open"          # 서킷 열림 - 요청 차단
    HALF_OPEN = "half_open"  # 반개방 - 테스트 요청 허용


@dataclass
class CircuitBreakerConfig:
    """Circuit Breaker 설정"""
    failure_threshold: int = 5        # 실패 임계값 (이 횟수 이상 실패 시 서킷 열림)
    success_threshold: int = 2         # 성공 임계값 (반개방 상태에서 성공 시 닫힘)
    timeout_seconds: int = 60          # 서킷 열림 지속 시간 (초)
    half_open_max_calls: int = 3       # 반개방 상태에서 허용되는 최대 호출 수
    excluded_exceptions: tuple = ()    # 서킷 트립에서 제외할 예외 타입


@dataclass
class CircuitBreakerStats:
    """Circuit Breaker 통계"""
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changes: list = field(default_factory=list)
    
    def record_success(self):
        """성공 기록"""
        self.total_calls += 1
        self.total_successes += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
    
    def record_failure(self):
        """실패 기록"""
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = datetime.now()
    
    def reset_consecutive(self):
        """연속 카운터 리셋"""
        self.consecutive_failures = 0
        self.consecutive_successes = 0


class CircuitBreakerError(Exception):
    """서킷 브레이커 에러"""
    
    def __init__(self, message: str, remaining_seconds: float = 0):
        super().__init__(message)
        self.remaining_seconds = remaining_seconds


class CircuitBreaker:
    """Circuit Breaker 패턴 구현
    
    API 호출 등 외부 서비스 호출 시 연속 실패를 방지합니다.
    
    사용 예시:
        circuit = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))
        
        @circuit
        def call_api():
            response = requests.get("https://api.example.com")
            return response.json()
    """
    
    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        name: str = "default",
        on_state_change: Optional[Callable[[str, str], None]] = None,
        on_failure: Optional[Callable[[Exception], None]] = None
    ):
        """초기화
        
        Args:
            config: 서킷 브레이커 설정
            name: 서킷 브레이커 이름 (로깅용)
            on_state_change: 상태 변경 시 콜백 (old_state, new_state)
            on_failure: 실패 시 콜백 (exception)
        """
        self.config = config or CircuitBreakerConfig()
        self.name = name
        self.on_state_change = on_state_change
        self.on_failure = on_failure
        
        self._state = CircuitState.CLOSED
        self._opened_at: Optional[datetime] = None
        self._half_open_calls = 0
        self.stats = CircuitBreakerStats()
        self._lock = Lock()
    
    @property
    def state(self) -> CircuitState:
        """현재 상태 조회 (자동 상태 전이 포함)"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # 타임아웃 경과 확인
                if self._opened_at and datetime.now() >= self._opened_at + timedelta(seconds=self.config.timeout_seconds):
                    self._change_state(CircuitState.HALF_OPEN)
            return self._state
    
    def _change_state(self, new_state: CircuitState):
        """상태 변경"""
        if self._state == new_state:
            return
        
        old_state = self._state
        self._state = new_state
        
        # 상태별 초기화
        if new_state == CircuitState.OPEN:
            self._opened_at = datetime.now()
            logger.warning(f"[{self.name}] 서킷 OPEN! 연속 {self.stats.consecutive_failures}회 실패")
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            logger.info(f"[{self.name}] 서킷 HALF_OPEN - 복구 테스트 시작")
        elif new_state == CircuitState.CLOSED:
            self._opened_at = None
            self.stats.reset_consecutive()
            logger.info(f"[{self.name}] 서킷 CLOSED - 정상 복구")
        
        # 통계 기록
        self.stats.state_changes.append({
            'from': old_state.value,
            'to': new_state.value,
            'timestamp': datetime.now().isoformat()
        })
        
        # 콜백 호출
        if self.on_state_change:
            try:
                self.on_state_change(old_state.value, new_state.value)
            except Exception as e:
                logger.error(f"on_state_change 콜백 에러: {e}")
    
    def _can_execute(self) -> bool:
        """실행 가능 여부 확인"""
        state = self.state  # 상태 전이 트리거
        
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.OPEN:
            return False
        elif state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
        return False
    
    def _get_remaining_timeout(self) -> float:
        """남은 타임아웃 시간 (초)"""
        if self._state != CircuitState.OPEN or not self._opened_at:
            return 0.0
        
        elapsed = (datetime.now() - self._opened_at).total_seconds()
        remaining = self.config.timeout_seconds - elapsed
        return max(0.0, remaining)
    
    def _handle_success(self):
        """성공 처리"""
        with self._lock:
            self.stats.record_success()
            
            if self._state == CircuitState.HALF_OPEN:
                if self.stats.consecutive_successes >= self.config.success_threshold:
                    self._change_state(CircuitState.CLOSED)
    
    def _handle_failure(self, exception: Exception):
        """실패 처리"""
        # 제외 예외 체크
        if isinstance(exception, self.config.excluded_exceptions):
            return
        
        with self._lock:
            self.stats.record_failure()
            
            # 콜백 호출
            if self.on_failure:
                try:
                    self.on_failure(exception)
                except Exception as e:
                    logger.error(f"on_failure 콜백 에러: {e}")
            
            if self._state == CircuitState.HALF_OPEN:
                # 반개방 상태에서 실패 시 다시 열림
                self._change_state(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self.stats.consecutive_failures >= self.config.failure_threshold:
                    self._change_state(CircuitState.OPEN)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """함수 호출 (서킷 브레이커 적용)"""
        if not self._can_execute():
            remaining = self._get_remaining_timeout()
            raise CircuitBreakerError(
                f"서킷이 열려 있습니다. {remaining:.1f}초 후 재시도하세요.",
                remaining_seconds=remaining
            )
        
        try:
            result = func(*args, **kwargs)
            self._handle_success()
            return result
        except Exception as e:
            self._handle_failure(e)
            raise
    
    def __call__(self, func: Callable) -> Callable:
        """데코레이터로 사용"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def get_status(self) -> Dict[str, Any]:
        """상태 정보 조회"""
        return {
            'name': self.name,
            'state': self.state.value,
            'stats': {
                'total_calls': self.stats.total_calls,
                'total_successes': self.stats.total_successes,
                'total_failures': self.stats.total_failures,
                'consecutive_failures': self.stats.consecutive_failures,
                'success_rate': (self.stats.total_successes / self.stats.total_calls * 100) 
                               if self.stats.total_calls > 0 else 0.0
            },
            'remaining_timeout': self._get_remaining_timeout() if self._state == CircuitState.OPEN else 0,
            'last_failure': self.stats.last_failure_time.isoformat() if self.stats.last_failure_time else None
        }
    
    def reset(self):
        """수동 리셋"""
        with self._lock:
            self._change_state(CircuitState.CLOSED)
            self.stats = CircuitBreakerStats()
            logger.info(f"[{self.name}] 서킷 수동 리셋")


class CircuitBreakerRegistry:
    """서킷 브레이커 레지스트리
    
    여러 서킷 브레이커를 중앙에서 관리합니다.
    """
    
    _instance: Optional['CircuitBreakerRegistry'] = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._circuits: Dict[str, CircuitBreaker] = {}
            return cls._instance
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        **kwargs
    ) -> CircuitBreaker:
        """서킷 브레이커 조회 또는 생성"""
        if name not in self._circuits:
            self._circuits[name] = CircuitBreaker(
                config=config,
                name=name,
                **kwargs
            )
        return self._circuits[name]
    
    def get_all_status(self) -> Dict[str, Dict]:
        """모든 서킷 상태 조회"""
        return {name: circuit.get_status() for name, circuit in self._circuits.items()}
    
    def reset_all(self):
        """모든 서킷 리셋"""
        for circuit in self._circuits.values():
            circuit.reset()


# 전역 레지스트리
circuit_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str = "default", **kwargs) -> CircuitBreaker:
    """서킷 브레이커 가져오기 헬퍼 함수"""
    return circuit_registry.get_or_create(name, **kwargs)
