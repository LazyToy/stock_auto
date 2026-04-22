"""알림 서비스 (Notification)
"""

import requests
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {
    "디스코드_웹훅_URL",
    "봇토큰",
    "챗ID",
}


def _is_configured(value: Optional[str]) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return normalized not in _PLACEHOLDER_VALUES


def _get_config():
    from src.config import Config

    return Config


def send_discord_message(message: str, webhook_url: str = None) -> bool:
    """디스코드 웹훅으로 메시지 전송"""
    config = _get_config()
    url = webhook_url or config.DISCORD_WEBHOOK_URL
    if not _is_configured(url):
        logger.warning("Discord Webhook URL이 설정되지 않았습니다.")
        return False
        
    try:
        data = {
            "content": message,
            "username": "Stock Auto-Trader",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2855/2855263.png" # 봇 아이콘 (선택 사항)
        }
        
        headers = {"Content-Type": "application/json"}
        res = requests.post(url, data=json.dumps(data), headers=headers)
        
        if res.status_code == 204:
            logger.info("디스코드 알림 전송 성공")
            return True
        else:
            logger.error(f"디스코드 알림 전송 실패 ({res.status_code}): {res.text}")
            return False
            
    except Exception as e:
        logger.error(f"디스코드 연결 오류: {e}")
        return False

def send_telegram_message(message: str) -> bool:
    """텔레그램 봇 API로 메시지 전송"""
    config = _get_config()
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    
    if not _is_configured(token) or not _is_configured(chat_id):
        # logger.warning("텔레그램 설정이 없습니다.")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        res = requests.post(url, data=data)
        
        if res.status_code == 200:
            return True
        else:
            logger.error(f"텔레그램 전송 실패: {res.text}")
            return False
    except Exception as e:
        logger.error(f"텔레그램 연결 오류: {e}")
        return False

def send_notification(message: str) -> bool:
    """설정된 모든 채널로 알림 전송"""
    # 1. 터미널/로그
    logger.info(f"[Notification] {message}")
    
    success_discord = False
    success_telegram = False
    
    # 2. 디스코드 (우선)
    config = _get_config()

    if _is_configured(config.DISCORD_WEBHOOK_URL):
        success_discord = send_discord_message(message)
        
    # 3. 텔레그램 (차순위)
    if _is_configured(config.TELEGRAM_BOT_TOKEN) and _is_configured(config.TELEGRAM_CHAT_ID):
        success_telegram = send_telegram_message(message)
        
    return success_discord or success_telegram

