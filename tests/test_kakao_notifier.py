"""카카오톡 알림 테스트

카카오톡 API를 통해 거래 알림을 전송하는 기능을 테스트합니다.
"""

import unittest
from unittest.mock import Mock, patch

from src.utils.kakao_notifier import KakaoNotifier, NotificationType, TradeNotification


class TestKakaoNotifier(unittest.TestCase):
    """카카오톡 알림 테스트"""

    def setUp(self):
        self.notifier = KakaoNotifier(
            rest_api_key="test_key", redirect_uri="http://localhost:8080", access_token="test_token"
        )

    def test_format_trade_message(self):
        """거래 알림 메시지 포맷 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.ORDER_EXECUTED,
            symbol="005930",
            action="BUY",
            quantity=10,
            price=75000,
            reason="리밸런싱",
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
            reason="손절매 신호",
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
            reason="AI 코파일럿 추천",
        )

        message = self.notifier.format_message(notification)

        # 승인 링크가 포함되어 있는지 확인
        self.assertIn("승인", message)

    def test_send_message_refreshes_token_and_retries_on_401(self):
        """401 응답을 받으면 토큰 갱신 후 메시지를 1회 재시도한다."""
        self.notifier._refresh_token = "refresh_token"
        first_response = Mock()
        first_response.status_code = 401
        second_response = Mock()
        second_response.status_code = 200

        with patch(
            "src.utils.kakao_notifier.requests.post",
            side_effect=[first_response, second_response],
        ) as mock_post:
            with patch.object(self.notifier, "refresh_access_token", return_value=True) as refresh:
                sent = self.notifier.send_message("테스트 메시지")

        self.assertTrue(sent)
        refresh.assert_called_once()
        self.assertEqual(mock_post.call_count, 2)

    def test_init_uses_env_rest_key_instead_of_hardcoded_value(self):
        with patch.dict(
            "os.environ",
            {"KAKAO_REST_API_KEY": "env_rest_key"},
            clear=False,
        ):
            notifier = KakaoNotifier()

        self.assertEqual(notifier.rest_api_key, "env_rest_key")

    def test_get_token_includes_client_secret_when_configured(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "access_token": "access",
            "refresh_token": "refresh",
        }

        notifier = KakaoNotifier(
            rest_api_key="rest_key",
            access_token="",
            refresh_token="",
            client_secret="client_secret",
        )

        with patch("src.utils.kakao_notifier.requests.post", return_value=response) as mock_post:
            self.assertTrue(notifier.get_token("auth_code"))

        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(data["client_secret"], "client_secret")
        self.assertEqual(notifier._access_token, "access")
        self.assertEqual(notifier._refresh_token, "refresh")


class TestTradeNotification(unittest.TestCase):
    """거래 알림 DTO 테스트"""

    def test_notification_creation(self):
        """알림 객체 생성 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.ORDER_EXECUTED,
            symbol="005930",
            action="BUY",
            quantity=10,
            price=75000,
        )

        self.assertEqual(notification.symbol, "005930")
        self.assertEqual(notification.action, "BUY")

    def test_notification_with_optional_fields(self):
        """선택 필드가 있는 알림 객체 테스트"""
        notification = TradeNotification(
            notification_type=NotificationType.SYSTEM_ERROR,
            symbol="",
            action="",
            reason="API 연결 실패",
        )

        self.assertEqual(notification.notification_type, NotificationType.SYSTEM_ERROR)
        self.assertEqual(notification.reason, "API 연결 실패")


if __name__ == "__main__":
    unittest.main()
