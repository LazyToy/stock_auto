"""Notification helpers for Discord and Telegram."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {
    "",
    "<discord_webhook_url>",
    "<telegram_bot_token>",
    "<telegram_chat_id>",
    "YOUR_DISCORD_WEBHOOK_URL",
    "YOUR_TELEGRAM_BOT_TOKEN",
    "YOUR_TELEGRAM_CHAT_ID",
}


def _is_configured(value: Optional[str]) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return normalized not in _PLACEHOLDER_VALUES


def _is_telegram_configured(token: Optional[str], chat_id: Optional[str]) -> bool:
    if not _is_configured(token) or not _is_configured(chat_id):
        return False
    return ":" in str(token)


def _is_discord_webhook_configured(webhook_url: Optional[str]) -> bool:
    if not _is_configured(webhook_url):
        return False
    normalized = str(webhook_url).strip().lower()
    return normalized.startswith("https://") or normalized.startswith("http://")


def _get_config():
    from src.config import Config

    return Config


def _redact_sensitive_text(value: object) -> str:
    """Remove tokens and webhook paths from exception/log text."""
    text = str(value)
    text = re.sub(r"bot[^/\s]+/sendMessage", "bot<redacted>/sendMessage", text)
    text = re.sub(
        r"https://discord(?:app)?\.com/api/webhooks/[^\s]+",
        "https://discord.com/api/webhooks/<redacted>",
        text,
    )
    return text


def send_discord_message(message: str, webhook_url: str = None) -> bool:
    """Send a message to Discord using a configured webhook URL."""
    config = _get_config()
    url = webhook_url or config.DISCORD_WEBHOOK_URL
    if not _is_discord_webhook_configured(url):
        logger.warning("Discord webhook URL is not configured.")
        return False

    try:
        data = {
            "content": message,
            "username": "Stock Auto-Trader",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2855/2855263.png",
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(url, data=json.dumps(data), headers=headers)

        if res.status_code == 204:
            logger.info("Discord notification sent successfully.")
            return True
        logger.error(
            "Discord notification failed (%s): %s",
            res.status_code,
            _redact_sensitive_text(res.text),
        )
        return False
    except Exception as exc:
        logger.error("Discord connection error: %s", _redact_sensitive_text(exc))
        return False


def send_telegram_message(message: str) -> bool:
    """Send a message using the Telegram Bot API."""
    config = _get_config()
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not _is_telegram_configured(token, chat_id):
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        res = requests.post(url, data=data)

        if res.status_code == 200:
            return True
        logger.error("Telegram send failed: %s", _redact_sensitive_text(res.text))
        return False
    except Exception as exc:
        logger.error("Telegram connection error: %s", _redact_sensitive_text(exc))
        return False


def send_notification(message: str) -> bool:
    """Send a notification to every configured channel."""
    logger.info("[Notification] %s", message)

    success_discord = False
    success_telegram = False
    config = _get_config()

    if _is_discord_webhook_configured(config.DISCORD_WEBHOOK_URL):
        success_discord = send_discord_message(message)

    if _is_telegram_configured(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID):
        success_telegram = send_telegram_message(message)

    return success_discord or success_telegram
