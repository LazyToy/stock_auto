"""Self-Healing Trading Engine

장애 발생 시 자동 복구 및 Saga 패턴 보상 트랜잭션을 제공합니다.

주요 기능:
1. 상태 머신 기반 거래 상태 관리
2. 부분 체결 시 잔량 취소 또는 시장가 청산
3. 타임아웃 시 자동 복구
4. 보상 트랜잭션 (Compensating Transaction)
"""

import logging
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger("SelfHealing")


class TradingState(Enum):
    """거래 상태 열거형"""
    IDLE = "IDLE"                      # 대기 상태
    PLACING = "PLACING"                # 주문 제출 중
    PENDING = "PENDING"                # 주문 접수됨 (미체결)
    PARTIAL_FILL = "PARTIAL_FILL"      # 부분 체결
    FILLED = "FILLED"                  # 전량 체결
    HEDGING = "HEDGING"                # 헤지 포지션 진입 중
    RECOVERING = "RECOVERING"          # 복구 진행 중
    COMPLETE = "COMPLETE"              # 완료
    FAILED = "FAILED"                  # 실패


@dataclass
class OrderContext:
    """주문 컨텍스트"""
    symbol: str
    quantity: int
    side: str  # "BUY" or "SELL"
    price: float
    order_id: Optional[str] = None
    timeout_seconds: int = 300  # 기본 5분 타임아웃
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryAction:
    """복구 액션"""
    action_type: str  # "CANCEL_REMAINING", "MARKET_SELL", "MARKET_BUY", "HEDGE"
    symbol: str
    quantity: int
    order_id: Optional[str] = None
    price: Optional[float] = None
    reason: str = ""


class TradingStateMachine:
    """거래 상태 머신"""
    
    def __init__(self):
        self._state = TradingState.IDLE
        self._context: Optional[OrderContext] = None
        self._filled_quantity = 0
        self._history: List[Dict[str, Any]] = []
        self._state_handlers: Dict[TradingState, Callable] = {}
        
    @property
    def current_state(self) -> TradingState:
        return self._state
    
    @property
    def filled_quantity(self) -> int:
        return self._filled_quantity
    
    @property
    def context(self) -> Optional[OrderContext]:
        return self._context
    
    def _transition(self, new_state: TradingState, reason: str = ""):
        """상태 전환"""
        old_state = self._state
        self._state = new_state
        
        # 히스토리 기록
        self._history.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        })
        
        logger.info(f"상태 전환: {old_state.value} -> {new_state.value} ({reason})")
    
    def place_order(self, context: OrderContext):
        """주문 제출"""
        if self._state != TradingState.IDLE:
            raise ValueError(f"Invalid state for placing order: {self._state}")
        
        self._context = context
        self._filled_quantity = 0
        self._transition(TradingState.PLACING, f"주문 제출: {context.symbol}")
    
    def on_order_accepted(self, order_id: str):
        """주문 접수됨"""
        if self._context:
            self._context.order_id = order_id
        self._transition(TradingState.PENDING, f"주문 접수: {order_id}")
    
    def on_partial_fill(self, filled_qty: int, remaining_qty: int):
        """부분 체결"""
        self._filled_quantity = filled_qty
        self._transition(
            TradingState.PARTIAL_FILL, 
            f"부분 체결: {filled_qty}/{self._context.quantity if self._context else '?'}"
        )
    
    def on_complete(self):
        """전량 체결 완료"""
        if self._context:
            self._filled_quantity = self._context.quantity
        self._transition(TradingState.COMPLETE, "전량 체결")
    
    def on_fill(self):
        """체결됨"""
        if self._context:
            self._filled_quantity = self._context.quantity
        self._transition(TradingState.FILLED, "체결됨")
    
    def on_recovery_start(self, reason: str = ""):
        """복구 시작"""
        self._transition(TradingState.RECOVERING, reason)
    
    def on_hedging_start(self):
        """헤지 포지션 시작"""
        self._transition(TradingState.HEDGING, "헤지 포지션 진입")
    
    def on_fail(self, reason: str = ""):
        """실패"""
        self._transition(TradingState.FAILED, reason)
    
    def reset(self):
        """상태 초기화"""
        self._state = TradingState.IDLE
        self._context = None
        self._filled_quantity = 0
        self._history = []


class SagaOrchestrator:
    """Saga 패턴 오케스트레이터
    
    장애 발생 시 보상 트랜잭션을 조율합니다.
    """
    
    def __init__(self, default_timeout_seconds: int = 300):
        self.default_timeout = default_timeout_seconds
        self._compensation_log: List[RecoveryAction] = []
    
    def create_compensation(
        self, 
        context: OrderContext, 
        filled_qty: int, 
        remaining_qty: int
    ) -> RecoveryAction:
        """
        부분 체결에 대한 보상 액션 생성
        
        전략: 잔량 취소 (가장 안전한 방법)
        - 부분 체결된 물량은 유지
        - 미체결 잔량만 취소
        """
        action = RecoveryAction(
            action_type="CANCEL_REMAINING",
            symbol=context.symbol,
            quantity=remaining_qty,
            order_id=context.order_id,
            reason=f"부분 체결 {filled_qty}주 후 잔량 {remaining_qty}주 취소"
        )
        
        self._compensation_log.append(action)
        logger.info(f"보상 액션 생성: {action}")
        
        return action
    
    def create_rollback(self, context: OrderContext, filled_qty: int) -> RecoveryAction:
        """
        롤백 액션 생성 (전량 체결 후 되돌리기)
        
        전략: 시장가 반대 포지션
        - BUY -> MARKET_SELL
        - SELL -> MARKET_BUY
        """
        opposite_side = "MARKET_SELL" if context.side == "BUY" else "MARKET_BUY"
        
        action = RecoveryAction(
            action_type=opposite_side,
            symbol=context.symbol,
            quantity=filled_qty,
            order_id=None,  # 새 주문
            reason=f"롤백: {context.side} {filled_qty}주 청산"
        )
        
        self._compensation_log.append(action)
        logger.warning(f"롤백 액션 생성: {action}")
        
        return action
    
    def check_timeout(self, context: OrderContext, elapsed_seconds: int) -> bool:
        """
        타임아웃 체크
        
        Returns:
            bool: 타임아웃 발생 여부
        """
        timeout = context.timeout_seconds or self.default_timeout
        
        if elapsed_seconds > timeout:
            logger.warning(f"타임아웃 발생: {context.symbol} ({elapsed_seconds}s > {timeout}s)")
            return True
        return False
    
    def get_compensation_history(self) -> List[RecoveryAction]:
        """보상 액션 히스토리 반환"""
        return self._compensation_log.copy()
    
    def clear_history(self):
        """히스토리 초기화"""
        self._compensation_log = []


class SelfHealingEngine:
    """Self-Healing 트레이딩 엔진

    상태 머신과 Saga 오케스트레이터를 조합하여
    장애에 강인한 거래 실행을 제공합니다.
    """

    def __init__(
        self,
        api_client,  # KISAPIClient
        timeout_seconds: int = 300,
        recovery_enabled: bool = True,
        broker=None,  # BaseBroker (선택적)
    ):
        self.api_client = api_client
        self.broker = broker  # 실제 주문 실행용 브로커 (None이면 graceful degradation)
        self.state_machine = TradingStateMachine()
        self.saga = SagaOrchestrator(default_timeout_seconds=timeout_seconds)
        self.recovery_enabled = recovery_enabled
        self._pending_recoveries: List[RecoveryAction] = []
    
    def execute_order(self, context: OrderContext) -> bool:
        """
        자기 복구 기능이 있는 주문 실행
        
        Returns:
            bool: 성공 여부
        """
        try:
            # 1. 상태 머신 시작
            self.state_machine.place_order(context)
            
            # 2. 주문 제출
            order_id = self._submit_order(context)
            
            if order_id:
                self.state_machine.on_order_accepted(order_id)
                context.order_id = order_id
                
                # 3. 체결 대기 및 모니터링
                success = self._monitor_order(context)
                
                if success:
                    self.state_machine.on_complete()
                    return True
                else:
                    # 복구 필요
                    return self._handle_recovery(context)
            else:
                self.state_machine.on_fail("주문 제출 실패")
                return False
                
        except Exception as e:
            logger.error(f"주문 실행 오류: {e}")
            self.state_machine.on_fail(str(e))
            
            if self.recovery_enabled:
                return self._handle_recovery(context)
            return False
    
    def _submit_order(self, context: OrderContext) -> Optional[str]:
        """주문 제출 (API 호출)"""
        try:
            logger.info(f"주문 제출: {context.side} {context.symbol} {context.quantity}주 @ {context.price}")

            # broker가 있으면 실제 주문 실행
            if self.broker is not None:
                from src.data.models import Order, OrderSide, OrderType
                order = Order(
                    symbol=context.symbol,
                    side=OrderSide.BUY if context.side == "BUY" else OrderSide.SELL,
                    order_type=OrderType.LIMIT if context.price else OrderType.MARKET,
                    price=context.price or 0,
                    quantity=context.quantity,
                    created_at=datetime.now(),
                )
                order_id = self.broker.place_order(
                    order,
                    exchange=context.metadata.get("exchange", "NASD"),
                )
                logger.info(f"실제 주문 완료: order_id={order_id}")
                return str(order_id)

            # broker가 없으면 api_client 직접 사용 (호환성 유지)
            if self.api_client is not None:
                from src.data.models import Order, OrderSide, OrderType
                order = Order(
                    symbol=context.symbol,
                    side=OrderSide.BUY if context.side == "BUY" else OrderSide.SELL,
                    order_type=OrderType.LIMIT if context.price else OrderType.MARKET,
                    price=context.price or 0,
                    quantity=context.quantity,
                    created_at=datetime.now(),
                )
                exchange = context.metadata.get("exchange")
                if exchange:
                    order_id = self.api_client.place_order(order, exchange=exchange)
                else:
                    order_id = self.api_client.place_order(order)
                if order_id:
                    logger.info(f"API 주문 완료: order_id={order_id}")
                    return str(order_id)

            # 둘 다 없으면 시뮬레이션용 mock ID 반환
            logger.warning("broker/api_client 미설정 - 시뮬레이션 모드로 실행")
            return f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        except Exception as e:
            logger.error(f"주문 제출 실패: {e}")
            return None
    
    def _monitor_order(self, context: OrderContext) -> bool:
        """주문 체결 모니터링"""
        # 실제로는 폴링 또는 WebSocket으로 체결 상태 확인
        # 여기서는 시뮬레이션
        return True
    
    def _handle_recovery(self, context: OrderContext) -> bool:
        """복구 처리"""
        logger.warning(f"복구 시작: {context.symbol}")
        
        # 현재 상태에 따른 복구 액션 결정
        current_state = self.state_machine.current_state
        filled_qty = self.state_machine.filled_quantity
        self.state_machine.on_recovery_start()
        
        if current_state == TradingState.PARTIAL_FILL:
            # 부분 체결: 잔량 취소
            remaining = context.quantity - filled_qty
            action = self.saga.create_compensation(context, filled_qty, remaining)
            self._execute_recovery_action(action)
            
        elif current_state in [TradingState.PLACING, TradingState.PENDING]:
            # 미체결: 전량 취소
            action = RecoveryAction(
                action_type="CANCEL_ALL",
                symbol=context.symbol,
                quantity=context.quantity,
                order_id=context.order_id,
                reason="주문 취소"
            )
            self._execute_recovery_action(action)
        
        self.state_machine.reset()
        return True
    
    def _execute_recovery_action(self, action: RecoveryAction):
        """복구 액션 실행"""
        logger.info(f"복구 액션 실행: {action.action_type} {action.symbol} {action.quantity}주")

        if action.action_type in ("CANCEL_REMAINING", "CANCEL_ALL"):
            # 잔량/전량 취소 API 호출
            if action.order_id is None:
                logger.warning(f"취소할 order_id가 없습니다: {action.symbol} ({action.action_type})")
                return
            try:
                if self.broker is not None:
                    # broker 인터페이스에 cancel_order가 있으면 사용
                    cancel_fn = getattr(self.broker, "cancel_order", None)
                    if callable(cancel_fn):
                        cancel_fn(action.order_id, action.symbol, action.quantity)
                        logger.info(f"broker.cancel_order 완료: {action.order_id}")
                    else:
                        logger.warning("broker에 cancel_order 메서드가 없습니다.")
                elif self.api_client is not None:
                    cancel_fn = getattr(self.api_client, "cancel_order", None)
                    if callable(cancel_fn):
                        cancel_fn(action.order_id, action.symbol, action.quantity)
                        logger.info(f"api_client.cancel_order 완료: {action.order_id}")
                    else:
                        logger.warning("api_client에 cancel_order 메서드가 없습니다.")
                else:
                    logger.warning(f"broker/api_client 미설정 - 취소 스킵: {action.order_id}")
            except Exception as e:
                logger.error(f"주문 취소 실패 ({action.action_type}): {e}")

        elif action.action_type in ("MARKET_SELL", "MARKET_BUY"):
            # 시장가 반대 포지션 진입
            side = "SELL" if action.action_type == "MARKET_SELL" else "BUY"
            market_context = OrderContext(
                symbol=action.symbol,
                quantity=action.quantity,
                side=side,
                price=0,  # 시장가
                timeout_seconds=60,
            )
            try:
                if self.broker is not None or self.api_client is not None:
                    order_id = self._submit_order(market_context)
                    if order_id:
                        logger.info(f"시장가 {side} 복구 주문 완료: {action.symbol} {action.quantity}주, order_id={order_id}")
                    else:
                        logger.error(f"시장가 {side} 복구 주문 실패: {action.symbol}")
                else:
                    logger.warning(f"broker/api_client 미설정 - 시장가 {side} 스킵: {action.symbol}")
            except Exception as e:
                logger.error(f"시장가 {side} 복구 주문 오류: {e}")


# 전역 인스턴스 (싱글톤)
_global_engine: Optional[SelfHealingEngine] = None


def get_self_healing_engine(api_client=None, broker=None) -> SelfHealingEngine:
    """전역 Self-Healing 엔진 인스턴스 반환"""
    global _global_engine
    if _global_engine is None:
        _global_engine = SelfHealingEngine(api_client, broker=broker)
    return _global_engine
