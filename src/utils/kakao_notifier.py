"""카카오톡 알림 모듈

카카오톡 API를 통해 거래 알림, 시그널 알림, 승인 요청을 전송합니다.

카카오 개발자 설정:
1. https://developers.kakao.com/ 접속
2. 애플리케이션 추가
3. 카카오 로그인 활성화
4. Redirect URI 등록 (예: http://localhost:8080)
5. 동의항목에서 "카카오톡 메시지 전송" 활성화
6. REST API 키를 .env 파일에 KAKAO_REST_API_KEY=xxx 로 저장
"""

import os
import logging
import requests
import webbrowser
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from urllib.parse import urlencode

logger = logging.getLogger("KakaoNotifier")


class NotificationType(Enum):
    """알림 유형"""
    ORDER_EXECUTED = "주문체결"          # 주문 체결
    SIGNAL_ALERT = "시그널알림"          # 매수/매도 시그널
    APPROVAL_REQUEST = "승인요청"        # 원터치 승인 요청
    DISCLOSURE_ALERT = "공시알림"        # 중요 공시 알림
    SYSTEM_ERROR = "시스템오류"          # 시스템 오류
    DAILY_REPORT = "일일리포트"          # 일일 실적 리포트


@dataclass
class TradeNotification:
    """거래 알림"""
    notification_type: NotificationType
    symbol: str
    action: str
    quantity: int = 0
    price: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class KakaoNotifier:
    """카카오톡 알림 발송기
    
    카카오 REST API를 이용하여 '나에게 보내기' 메시지를 전송합니다.
    """
    
    AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    MESSAGE_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def __init__(
        self,
        rest_api_key: str = None,
        redirect_uri: str = "http://localhost:8080",
        access_token: str = None,
        refresh_token: str = None
    ):
        self.rest_api_key = rest_api_key or os.getenv("KAKAO_REST_API_KEY")
        self.redirect_uri = redirect_uri
        self._access_token = access_token or os.getenv("KAKAO_ACCESS_TOKEN")
        self._refresh_token = refresh_token or os.getenv("KAKAO_REFRESH_TOKEN")
        
        self.enabled = bool(self.rest_api_key)
        
        if not self.enabled:
            logger.warning("카카오 API 키가 설정되지 않았습니다. .env에 KAKAO_REST_API_KEY 추가 필요")
    
    @property
    def is_authenticated(self) -> bool:
        """인증 여부 확인"""
        return bool(self._access_token)
    
    def get_auth_url(self) -> str:
        """인증 URL 생성 (최초 1회 인증용)"""
        params = {
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "talk_message"
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"
    
    def authorize(self):
        """브라우저에서 인증 페이지 열기"""
        auth_url = self.get_auth_url()
        logger.info(f"브라우저에서 인증을 진행하세요: {auth_url}")
        webbrowser.open(auth_url)
    
    def get_token(self, auth_code: str) -> bool:
        """
        인증 코드로 토큰 발급
        
        Args:
            auth_code: authorize() 후 redirect에서 받은 code
            
        Returns:
            성공 여부
        """
        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.rest_api_key,
                    "redirect_uri": self.redirect_uri,
                    "code": auth_code
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            
            logger.info("카카오 토큰 발급 완료")
            logger.info(f"Access Token: {self._access_token[:20]}...")
            logger.info(f"Refresh Token: {self._refresh_token[:20]}...")
            logger.info("이 토큰을 .env 파일에 KAKAO_ACCESS_TOKEN, KAKAO_REFRESH_TOKEN으로 저장하세요.")
            
            return True
            
        except Exception as e:
            logger.error(f"토큰 발급 실패: {e}")
            return False
    
    def refresh_access_token(self) -> bool:
        """Access Token 갱신"""
        if not self._refresh_token:
            logger.error("Refresh Token이 없습니다.")
            return False
        
        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.rest_api_key,
                    "refresh_token": self._refresh_token
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data.get("access_token")
            
            # refresh_token도 갱신되었으면 업데이트
            if "refresh_token" in data:
                self._refresh_token = data["refresh_token"]
            
            logger.info("토큰 갱신 완료")
            return True
            
        except Exception as e:
            logger.error(f"토큰 갱신 실패: {e}")
            return False
    
    def send_message(self, message: str) -> bool:
        """
        카카오톡 메시지 전송 (나에게 보내기)
        
        Args:
            message: 전송할 메시지
            
        Returns:
            성공 여부
        """
        if not self.enabled or not self._access_token:
            logger.warning("카카오톡 알림이 비활성화되었거나 인증되지 않았습니다.")
            return False
        
        try:
            # 텍스트 메시지 템플릿
            template = {
                "object_type": "text",
                "text": message,
                "link": {
                    "web_url": "https://github.com",
                    "mobile_web_url": "https://github.com"
                }
            }
            
            response = requests.post(
                self.MESSAGE_URL,
                headers={"Authorization": f"Bearer {self._access_token}"},
                data={"template_object": str(template).replace("'", '"')},
                timeout=10
            )
            
            # 토큰 만료 시 갱신 후 재시도
            if response.status_code == 401:
                if self.refresh_access_token():
                    return self.send_message(message)
                return False
            
            response.raise_for_status()
            logger.info("카카오톡 메시지 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            return False
    
    def format_message(self, notification: TradeNotification) -> str:
        """알림을 카카오톡 메시지로 포맷팅"""
        emoji_map = {
            NotificationType.ORDER_EXECUTED: "📊",
            NotificationType.SIGNAL_ALERT: "🔔",
            NotificationType.APPROVAL_REQUEST: "⚡",
            NotificationType.DISCLOSURE_ALERT: "📰",
            NotificationType.SYSTEM_ERROR: "🚨",
            NotificationType.DAILY_REPORT: "📈"
        }
        
        emoji = emoji_map.get(notification.notification_type, "📌")
        
        # 기본 헤더
        lines = [
            f"{emoji} [{notification.notification_type.value}]",
            f"━━━━━━━━━━━━━━"
        ]
        
        # 종목 정보
        if notification.symbol:
            lines.append(f"종목: {notification.symbol}")
        
        # 행동
        if notification.action:
            action_emoji = "🔴" if notification.action == "SELL" else "🟢" if notification.action == "BUY" else "⚪"
            lines.append(f"액션: {action_emoji} {notification.action}")
        
        # 수량 및 가격
        if notification.quantity > 0:
            lines.append(f"수량: {notification.quantity}주")
        
        if notification.price > 0:
            lines.append(f"가격: {notification.price:,.0f}원")
        
        # 사유
        if notification.reason:
            lines.append(f"사유: {notification.reason}")
        
        # 시간
        lines.append(f"시간: {notification.timestamp.strftime('%H:%M:%S')}")
        
        # 승인 요청인 경우 승인 링크 추가
        if notification.notification_type == NotificationType.APPROVAL_REQUEST:
            lines.append("")
            lines.append("👉 [승인] 하시겠습니까?")
            lines.append("📱 앱에서 '승인' 버튼을 눌러주세요.")
        
        return "\n".join(lines)
    
    def send_trade_notification(self, notification: TradeNotification) -> bool:
        """거래 알림 전송"""
        message = self.format_message(notification)
        return self.send_message(message)
    
    def send_order_alert(
        self, 
        symbol: str, 
        action: str, 
        quantity: int, 
        price: float, 
        reason: str = ""
    ) -> bool:
        """주문 체결 알림 전송 (편의 메서드)"""
        notification = TradeNotification(
            notification_type=NotificationType.ORDER_EXECUTED,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            reason=reason
        )
        return self.send_trade_notification(notification)
    
    def send_signal_alert(self, symbol: str, action: str, reason: str) -> bool:
        """시그널 알림 전송 (편의 메서드)"""
        notification = TradeNotification(
            notification_type=NotificationType.SIGNAL_ALERT,
            symbol=symbol,
            action=action,
            reason=reason
        )
        return self.send_trade_notification(notification)
    
    def send_approval_request(
        self, 
        symbol: str, 
        action: str, 
        quantity: int, 
        price: float, 
        reason: str
    ) -> bool:
        """승인 요청 전송 (편의 메서드)"""
        notification = TradeNotification(
            notification_type=NotificationType.APPROVAL_REQUEST,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            reason=reason
        )
        return self.send_trade_notification(notification)
    
    def send_error_alert(self, error_message: str) -> bool:
        """시스템 오류 알림 전송"""
        notification = TradeNotification(
            notification_type=NotificationType.SYSTEM_ERROR,
            symbol="",
            action="",
            reason=error_message
        )
        return self.send_trade_notification(notification)


# 전역 인스턴스
_global_notifier: Optional[KakaoNotifier] = None


def get_kakao_notifier() -> KakaoNotifier:
    """전역 카카오톡 알림 인스턴스 반환"""
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = KakaoNotifier()
    return _global_notifier
