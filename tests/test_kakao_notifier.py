"""카카오톡 알림 테스트

카카오톡 API를 통해 거래 알림을 전송하는 기능을 테스트합니다.
"""

import unittest
from unittest.mock import Mock, patch
from src.utils.kakao_notifier import (
    KakaoNotifier,
    TradeNotification,
    NotificationType
)


class TestKakaoNotifier(unittest.TestCase):
    """카카오톡 알림 테스트"""
    
    def setUp(self):
        self.notifier = KakaoNotifier(
            rest_api_key="test_key",
            redirect_uri="http://localhost:8080",
            access_token="test_token"
        )
        
    def test_format_trade_message(self):
        """거래 알림 메시지 포맷 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.ORDER_EXECUTED,
            symbol="005930",
            action="BUY",
            quantity=10,
            price=75000,
            reason="리밸런싱"
        )
        
        message = self.notifier.format_message(notification)
        
        self.assertIn("005930", message)
        self.assertIn("BUY", message)
        self.assertIn("75,000", message)
        
    def test_format_signal_message(self):
        """시그널 알림 메시지 포맷 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.SIGNAL_ALERT,
            symbol="AAPL",
            action="SELL",
            reason="손절매 신호"
        )
        
        message = self.notifier.format_message(notification)
        
        self.assertIn("AAPL", message)
        self.assertIn("SELL", message)
        self.assertIn("손절매", message)
        
    def test_approval_link_generation(self):
        """원터치 승인 링크 생성 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.APPROVAL_REQUEST,
            symbol="035420",
            action="BUY",
            quantity=5,
            price=320000,
            reason="AI 코파일럿 추천"
        )
        
        message = self.notifier.format_message(notification)
        
        # 승인 링크가 포함되어 있는지 확인
        self.assertIn("승인", message)


class TestTradeNotification(unittest.TestCase):
    """거래 알림 DTO 테스트"""
    
    def test_notification_creation(self):
        """알림 객체 생성 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.ORDER_EXECUTED,
            symbol="005930",
            action="BUY",
            quantity=10,
            price=75000
        )
        
        self.assertEqual(notification.symbol, "005930")
        self.assertEqual(notification.action, "BUY")
        
    def test_notification_with_optional_fields(self):
        """선택 필드가 있는 알림 객체 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.SYSTEM_ERROR,
            symbol="",
            action="",
            reason="API 연결 실패"
        )
        
        self.assertEqual(notification.notification_type, NotificationType.SYSTEM_ERROR)
        self.assertEqual(notification.reason, "API 연결 실패")


if __name__ == '__main__':
    unittest.main()
