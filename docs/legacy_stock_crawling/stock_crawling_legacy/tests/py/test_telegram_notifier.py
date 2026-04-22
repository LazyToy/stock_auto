"""이슈 #8: Telegram 알림 단위 테스트."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def _fake_http_post_ok(url: str, body: dict) -> dict:
    """Telegram sendMessage 성공 응답 시뮬레이션."""
    return {"ok": True, "result": {"message_id": 1}}


def _fake_http_post_fail(url: str, body: dict) -> dict:
    return {"ok": False, "description": "Bad Request"}


def test_send_message_success():
    """정상 전송 시 True 반환."""
    from telegram_notifier import TelegramNotifier
    n = TelegramNotifier(token="FAKE_TOKEN", chat_id="12345",
                         http_post=_fake_http_post_ok)
    assert n.send_message("테스트 메시지") is True


def test_send_message_api_fail_returns_false():
    """API ok=False 시 False 반환 (예외 미전파)."""
    from telegram_notifier import TelegramNotifier
    n = TelegramNotifier(token="FAKE_TOKEN", chat_id="12345",
                         http_post=_fake_http_post_fail)
    assert n.send_message("실패 메시지") is False


def test_send_message_no_token_returns_false():
    """토큰 없을 때 False 반환 (실 API 호출 없음)."""
    from telegram_notifier import TelegramNotifier
    called = []
    def should_not_call(url, body):
        called.append(True)
        return {"ok": True}
    n = TelegramNotifier(token=None, chat_id="12345",
                         http_post=should_not_call)
    result = n.send_message("메시지")
    assert result is False
    assert called == []  # 실 호출 없음


def test_send_message_network_error_returns_false():
    """네트워크 오류 시 False 반환 (예외 삼킴)."""
    from telegram_notifier import TelegramNotifier
    def raise_error(url, body):
        raise ConnectionError("타임아웃")
    n = TelegramNotifier(token="TOKEN", chat_id="111",
                         http_post=raise_error)
    assert n.send_message("오류 상황") is False


def test_token_not_in_url_log():
    """전송 URL에 실제 토큰 값이 로그/stdout으로 노출되지 않는지 확인."""
    import io, sys
    from telegram_notifier import TelegramNotifier
    captured_urls = []
    def capture_post(url, body):
        captured_urls.append(url)
        return {"ok": True}
    n = TelegramNotifier(token="SECRET_TOKEN_12345", chat_id="99",
                         http_post=capture_post)
    captured_out = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured_out
    try:
        n.send_message("토큰 노출 테스트")
    finally:
        sys.stdout = old_stdout
    output = captured_out.getvalue()
    assert "SECRET_TOKEN_12345" not in output


def test_should_notify_kr_surge():
    """KR 급등주 >= 5건이면 알림 필요."""
    from telegram_notifier import should_notify_kr_surge
    assert should_notify_kr_surge(surge_count=5) is True
    assert should_notify_kr_surge(surge_count=4) is False


def test_should_notify_theme_cluster():
    """★★★★☆ 이상 테마클러스터 존재하면 True."""
    from telegram_notifier import should_notify_theme_cluster
    clusters_strong = [{"intensity_stars": "★★★★☆", "sector": "2차전지"}]
    clusters_weak = [{"intensity_stars": "★★★☆☆", "sector": "바이오"}]
    assert should_notify_theme_cluster(clusters_strong) is True
    assert should_notify_theme_cluster(clusters_weak) is False
    assert should_notify_theme_cluster([]) is False


def test_format_surge_message():
    """급등주 요약 메시지 포맷 검증."""
    from telegram_notifier import format_surge_message
    msg = format_surge_message(date="2026-04-17", surge_count=7,
                               top_tickers=["A", "B", "C"])
    assert "2026-04-17" in msg
    assert "7" in msg


if __name__ == "__main__":
    test_send_message_success()
    test_send_message_api_fail_returns_false()
    test_send_message_no_token_returns_false()
    test_send_message_network_error_returns_false()
    test_token_not_in_url_log()
    test_should_notify_kr_surge()
    test_should_notify_theme_cluster()
    test_format_surge_message()
    print("[PASS] test_telegram_notifier 전체 통과")
