import logging

from src.utils import notification


def test_send_telegram_message_redacts_token_from_exception_logs(monkeypatch, caplog):
    token = "123456:secret-token-123"

    class Config:
        TELEGRAM_BOT_TOKEN = token
        TELEGRAM_CHAT_ID = "chat-456"
        DISCORD_WEBHOOK_URL = ""

    def failing_post(url, data=None):
        raise RuntimeError(f"failed connecting to {url}")

    monkeypatch.setattr(notification, "_get_config", lambda: Config)
    monkeypatch.setattr(notification.requests, "post", failing_post)

    with caplog.at_level(logging.ERROR):
        assert notification.send_telegram_message("hello") is False

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in logged
    assert "bot<redacted>" in logged


def test_send_discord_message_redacts_webhook_url_from_exception_logs(monkeypatch, caplog):
    webhook = "https://discord.com/api/webhooks/abc/secret-webhook"

    class Config:
        TELEGRAM_BOT_TOKEN = ""
        TELEGRAM_CHAT_ID = ""
        DISCORD_WEBHOOK_URL = webhook

    def failing_post(url, data=None, headers=None):
        raise RuntimeError(f"failed connecting to {url}")

    monkeypatch.setattr(notification, "_get_config", lambda: Config)
    monkeypatch.setattr(notification.requests, "post", failing_post)

    with caplog.at_level(logging.ERROR):
        assert notification.send_discord_message("hello") is False

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert webhook not in logged
    assert "webhooks/<redacted>" in logged


def test_discord_placeholder_without_url_scheme_is_not_configured(monkeypatch):
    calls = []

    class Config:
        TELEGRAM_BOT_TOKEN = ""
        TELEGRAM_CHAT_ID = ""
        DISCORD_WEBHOOK_URL = "디스코드_웹훅_URL"

    def unexpected_post(*args, **kwargs):
        calls.append(args)
        raise AssertionError("placeholder webhook should not be called")

    monkeypatch.setattr(notification, "_get_config", lambda: Config)
    monkeypatch.setattr(notification.requests, "post", unexpected_post)

    assert notification.send_notification("hello") is False
    assert calls == []
