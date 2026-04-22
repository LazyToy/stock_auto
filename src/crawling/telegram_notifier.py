"""
이슈 #8: Telegram 알림 연동.

urllib 기반, 외부 SDK 미사용.
http_post 를 injectable 로 받아 테스트 가능하게 설계.
토큰은 절대 로그에 출력하지 않는다.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable

_TIMEOUT = 10  # 초
_STRONG_INTENSITIES = {"★★★★☆", "★★★★★"}


def _default_http_post(url: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


class TelegramNotifier:
    """Telegram Bot API sendMessage 래퍼."""

    def __init__(
        self,
        token: str | None,
        chat_id: str,
        http_post: Callable[[str, dict], dict] = _default_http_post,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._http_post = http_post

    def send_message(self, text: str) -> bool:
        """메시지 전송. 성공 True, 실패/토큰없음 False."""
        if not self._token:
            return False
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        body = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}
        try:
            resp = self._http_post(url, body)
            return bool(resp.get("ok"))
        except Exception as exc:
            masked = f"****{self._token[-4:]}" if self._token else "없음"
            print(f"[Telegram] 전송 실패 (토큰 끝: {masked}): {exc}")
            return False


# ---------------------------------------------------------------------------
# 알림 판단 순수 함수
# ---------------------------------------------------------------------------

def should_notify_kr_surge(surge_count: int, threshold: int = 5) -> bool:
    """KR 급등주가 threshold 이상이면 True."""
    return surge_count >= threshold


def should_notify_theme_cluster(clusters: list[dict]) -> bool:
    """★★★★☆ 이상 클러스터가 하나라도 있으면 True."""
    return any(c.get("intensity_stars") in _STRONG_INTENSITIES for c in clusters)


def format_surge_message(date: str, surge_count: int, top_tickers: list[str]) -> str:
    """급등주 요약 메시지 생성."""
    tickers_str = ", ".join(top_tickers[:5])
    return (
        f"📈 <b>[KR 급등주 알림]</b> {date}\n"
        f"급등 종목 {surge_count}건 감지\n"
        f"주요 종목: {tickers_str}"
    )


def format_theme_message(date: str, cluster: dict) -> str:
    """강한 테마클러스터 알림 메시지 생성."""
    return (
        f"🔥 <b>[테마 급등]</b> {date}\n"
        f"섹터: {cluster.get('sector', '')}\n"
        f"강도: {cluster.get('intensity_stars', '')}\n"
        f"종목수: {cluster.get('ticker_count', '')}"
    )


def format_error_message(context: str, error: str) -> str:
    """파이프라인 오류 알림 메시지 생성."""
    return f"❌ <b>[파이프라인 오류]</b>\n컨텍스트: {context}\n오류: {error[:200]}"


def load_telegram_config(env_path: str = ".env.local") -> tuple[str | None, str | None]:
    """
    .env.local 에서 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 파싱.
    gemini_client.load_api_key 와 동일 패턴.
    """
    token: str | None = None
    chat_id: str | None = None
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "TELEGRAM_BOT_TOKEN":
                    token = val or None
                elif key == "TELEGRAM_CHAT_ID":
                    chat_id = val or None
    except FileNotFoundError:
        pass
    return token, chat_id
