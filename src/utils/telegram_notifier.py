"""텔레그램 알림 봇

자동 매매 시스템의 주요 이벤트를 텔레그램으로 알림합니다.

사용법:
    1. BotFather에서 봇 생성 후 토큰 획득
    2. 봇과 대화 시작 후 chat_id 확인
    3. 환경변수 설정: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    
    notifier = TelegramNotifier()
    notifier.send_message("테스트 메시지")
"""

import os
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """알림 레벨"""
    INFO = "ℹ️"      # 일반 정보
    SUCCESS = "✅"   # 성공
    WARNING = "⚠️"   # 경고
    ERROR = "🚨"     # 에러
    TRADE = "💰"     # 거래 체결


@dataclass
class TradeAlert:
    """거래 알림 데이터"""
    symbol: str
    action: str      # BUY / SELL
    quantity: int
    price: float
    reason: str
    profit_pct: Optional[float] = None


class TelegramNotifier:
    """텔레그램 알림 봇
    
    주요 기능:
    - 거래 체결 알림 (매수/매도)
    - 손절/익절 알림
    - 리밸런싱 알림
    - 시스템 오류 알림
    - 일일 리포트
    """
    
    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
    
    def __init__(
        self, 
        bot_token: str = None, 
        chat_id: str = None,
        enabled: bool = True
    ):
        """초기화
        
        Args:
            bot_token: 텔레그램 봇 토큰 (없으면 환경변수 TELEGRAM_BOT_TOKEN)
            chat_id: 텔레그램 채팅 ID (없으면 환경변수 TELEGRAM_CHAT_ID)
            enabled: 알림 활성화 여부
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = enabled
        
        if not self.bot_token or not self.chat_id:
            logger.warning("텔레그램 설정이 완료되지 않았습니다. 알림이 비활성화됩니다.")
            self.enabled = False
    
    def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        """텔레그램 메시지 전송
        
        Args:
            message: 전송할 메시지
            parse_mode: 파싱 모드 (Markdown / HTML)
            
        Returns:
            성공 여부
        """
        if not self.enabled:
            logger.debug(f"[텔레그램 비활성화] {message}")
            return False
        
        try:
            url = self.TELEGRAM_API_URL.format(token=self.bot_token)
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"텔레그램 알림 전송 성공")
                return True
            else:
                logger.error(f"텔레그램 알림 전송 실패: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"텔레그램 알림 오류: {e}")
            return False
    
    def send_alert(self, level: AlertLevel, title: str, message: str) -> bool:
        """레벨별 알림 전송
        
        Args:
            level: 알림 레벨
            title: 제목
            message: 내용
        """
        formatted = f"{level.value} *{title}*\n\n{message}"
        return self.send_message(formatted)
    
    def send_trade_alert(self, trade: TradeAlert) -> bool:
        """거래 알림 전송"""
        action_emoji = "🟢 매수" if trade.action == "BUY" else "🔴 매도"
        
        message = f"""
{action_emoji} *{trade.symbol}*

📊 *거래 정보*
• 수량: {trade.quantity:,}주
• 가격: {trade.price:,.0f}원
• 사유: {trade.reason}
"""
        
        if trade.profit_pct is not None:
            profit_emoji = "📈" if trade.profit_pct > 0 else "📉"
            message += f"• 수익률: {profit_emoji} {trade.profit_pct:+.2f}%\n"
        
        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self.send_message(message)
    
    def send_stop_loss_alert(self, symbol: str, loss_pct: float, quantity: int) -> bool:
        """손절매 알림"""
        message = f"""
🛑 *손절매 발동*

• 종목: {symbol}
• 손실률: {loss_pct*100:.2f}%
• 매도 수량: {quantity:,}주

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def send_trailing_stop_alert(self, symbol: str, profit_pct: float, drop_pct: float, quantity: int) -> bool:
        """트레일링 스탑 알림"""
        message = f"""
📉 *트레일링 스탑 발동*

• 종목: {symbol}
• 현재 수익률: {profit_pct*100:.2f}%
• 고점 대비 하락: {drop_pct*100:.2f}%
• 매도 수량: {quantity:,}주

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def send_daily_report(self, report: Dict[str, Any]) -> bool:
        """일일 리포트 전송"""
        message = f"""
📊 *일일 매매 리포트*
{datetime.now().strftime('%Y-%m-%d')}

💰 *자산 현황*
• 총 자산: {report.get('total_asset', 0):,.0f}원
• 예수금: {report.get('deposit', 0):,.0f}원
• 보유 종목: {report.get('stock_count', 0)}개

📈 *오늘의 거래*
• 매수: {report.get('buy_count', 0)}건
• 매도: {report.get('sell_count', 0)}건
• 손절매: {report.get('stop_loss_count', 0)}건

📊 *수익률*
• 일일 수익률: {report.get('daily_return', 0):+.2f}%
• 누적 수익률: {report.get('total_return', 0):+.2f}%
"""
        return self.send_message(message)
    
    def send_error_alert(self, error_type: str, error_message: str) -> bool:
        """시스템 오류 알림"""
        message = f"""
🚨 *시스템 오류 발생*

• 유형: {error_type}
• 메시지: {error_message}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def send_rebalance_alert(self, sells: list, buys: list) -> bool:
        """리밸런싱 알림"""
        sell_text = ", ".join(sells) if sells else "없음"
        buy_text = ", ".join(buys) if buys else "없음"
        
        message = f"""
🔄 *포트폴리오 리밸런싱*

🔴 *매도 종목*: {sell_text}
🟢 *매수 종목*: {buy_text}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)


# 전역 인스턴스 (싱글톤 패턴)
_notifier_instance: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """전역 TelegramNotifier 인스턴스 반환"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance
