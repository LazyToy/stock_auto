"""Self-Healing Trading Engine 테스트

장애 발생 시 자동 복구 및 Saga 패턴 보상 트랜잭션 기능을 테스트합니다.
"""

import unittest
from unittest.mock import Mock, patch
from datetime import datetime
from src.trader.self_healing import (
    TradingStateMachine, 
    TradingState, 
    OrderContext,
    RecoveryAction,
    SagaOrchestrator
)


class TestTradingStateMachine(unittest.TestCase):
    """트레이딩 상태 머신 테스트"""
    
    def setUp(self):
        self.state_machine = TradingStateMachine()
        
    def test_initial_state_is_idle(self):
        """초기 상태가 IDLE인지 확인"""
        self.assertEqual(self.state_machine.current_state, TradingState.IDLE)
        
    def test_transition_to_placing(self):
        """IDLE -> PLACING 전환 테스트"""
        context = OrderContext(
            symbol="005930",
            quantity=10,
            side="BUY",
            price=75000
        )
        
        self.state_machine.place_order(context)
        self.assertEqual(self.state_machine.current_state, TradingState.PLACING)
        
    def test_transition_to_partial_fill(self):
        """PLACING -> PARTIAL_FILL 전환 테스트"""
        context = OrderContext(
            symbol="005930",
            quantity=10,
            side="BUY",
            price=75000
        )
        
        self.state_machine.place_order(context)
        self.state_machine.on_partial_fill(filled_qty=5, remaining_qty=5)
        
        self.assertEqual(self.state_machine.current_state, TradingState.PARTIAL_FILL)
        self.assertEqual(self.state_machine.filled_quantity, 5)
        
    def test_transition_to_complete(self):
        """전량 체결 시 COMPLETE 전환 테스트"""
        context = OrderContext(
            symbol="005930",
            quantity=10,
            side="BUY",
            price=75000
        )
        
        self.state_machine.place_order(context)
        self.state_machine.on_complete()
        
        self.assertEqual(self.state_machine.current_state, TradingState.COMPLETE)


class TestSagaOrchestrator(unittest.TestCase):
    """Saga 패턴 오케스트레이터 테스트"""
    
    def setUp(self):
        self.saga = SagaOrchestrator()
        
    def test_compensate_partial_fill_buy(self):
        """부분 체결 BUY 주문 보상 (잔량 취소)"""
        context = OrderContext(
            symbol="AAPL",
            quantity=100,
            side="BUY",
            price=150.0,
            order_id="ORD001"
        )
        
        # 50주만 체결된 상황
        action = self.saga.create_compensation(
            context,
            filled_qty=50,
            remaining_qty=50
        )
        
        self.assertEqual(action.action_type, "CANCEL_REMAINING")
        self.assertEqual(action.quantity, 50)
        
    def test_compensate_with_market_close(self):
        """시장가 청산 보상 액션 테스트"""
        context = OrderContext(
            symbol="MSFT",
            quantity=30,
            side="BUY",
            price=400.0,
            order_id="ORD002"
        )
        
        # 전량 체결 후 롤백 필요 시
        action = self.saga.create_rollback(context, filled_qty=30)
        
        self.assertEqual(action.action_type, "MARKET_SELL")
        self.assertEqual(action.quantity, 30)
        
    def test_timeout_triggers_recovery(self):
        """타임아웃 시 복구 트리거 테스트"""
        context = OrderContext(
            symbol="005930",
            quantity=20,
            side="SELL",
            price=80000,
            order_id="ORD003",
            timeout_seconds=5
        )
        
        # 타임아웃 시뮬레이션 (5분 초과)
        should_recover = self.saga.check_timeout(context, elapsed_seconds=310)
        
        self.assertTrue(should_recover)


class TestRecoveryAction(unittest.TestCase):
    """복구 액션 테스트"""
    
    def test_cancel_action(self):
        """취소 액션 생성"""
        action = RecoveryAction(
            action_type="CANCEL_REMAINING",
            symbol="005930",
            quantity=10,
            order_id="ORD001"
        )
        
        self.assertEqual(action.action_type, "CANCEL_REMAINING")
        
    def test_market_sell_action(self):
        """시장가 매도 액션 생성"""
        action = RecoveryAction(
            action_type="MARKET_SELL",
            symbol="AAPL",
            quantity=50,
            order_id=None
        )
        
        self.assertEqual(action.action_type, "MARKET_SELL")


if __name__ == '__main__':
    unittest.main()
