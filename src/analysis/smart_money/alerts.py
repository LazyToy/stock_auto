"""Smart Money 신호 알림 정책과 provider 전송 래퍼.

PR-13 범위:
    - BUY/SELL 신호를 Kakao 또는 Telegram provider로 전달한다.
    - cooldown, confidence threshold, confidence jump 재알림 정책을 적용한다.
    - notifier 실패는 warning으로 격리하고 분석 결과 흐름을 중단하지 않는다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Protocol, Sequence

from src.analysis.smart_money.models import SmartMoneySignal

logger = logging.getLogger(__name__)

DEFAULT_ALERT_STATE_PATH = Path("data") / "smart_money_alert_state.json"
STATE_NAMESPACE = "smart_money_alerts"
DEFAULT_TIMEFRAME = "multi"
SUPPORTED_PROVIDERS = {"kakao", "telegram"}
SUPPORTED_NOTIFY_SIGNALS = {"BUY", "SELL"}


class KakaoSignalNotifier(Protocol):
    """Smart Money Kakao 알림에 필요한 최소 provider 계약."""

    def send_signal_alert(self, symbol: str, action: str, reason: str) -> bool:
        """신호 알림을 전송한다."""


class TelegramMessageNotifier(Protocol):
    """Smart Money Telegram 알림에 필요한 최소 provider 계약."""

    def send_message(self, message: str) -> bool:
        """메시지를 전송한다."""


class SystemAlertNotifier(Protocol):
    """Smart Money system alert provider 계약."""

    def send_error_alert(self, error_message: str) -> bool:
        """시스템 오류 알림을 전송한다."""


@dataclass(frozen=True)
class SmartMoneyAlertConfig:
    """Smart Money 알림 정책 설정."""

    enabled: bool = False
    provider: str = "kakao"
    cooldown_minutes: int = 30
    min_confidence: float = 0.60
    notify_on: tuple[str, ...] = ("BUY", "SELL")
    repeat_on_confidence_jump: bool = True
    confidence_jump_threshold: float = 0.15

    def __post_init__(self) -> None:
        """설정값의 타입과 범위를 보수적으로 검증한다."""
        if not isinstance(self.provider, str):
            raise ValueError("provider는 문자열이어야 합니다.")
        if isinstance(self.notify_on, str) or self.notify_on is None:
            raise ValueError("notify_on은 문자열 시퀀스이어야 합니다.")
        provider = self.provider.strip().lower()
        try:
            notify_on = tuple(_normalize_notify_signal(item) for item in self.notify_on)
        except TypeError as exc:
            raise ValueError("notify_on은 문자열 시퀀스이어야 합니다.") from exc
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"지원하지 않는 Smart Money 알림 provider입니다: {self.provider}")
        if self.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes는 0 이상이어야 합니다.")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence는 0.0 이상 1.0 이하이어야 합니다.")
        if not 0.0 <= self.confidence_jump_threshold <= 1.0:
            raise ValueError("confidence_jump_threshold는 0.0 이상 1.0 이하이어야 합니다.")
        if not notify_on:
            raise ValueError("notify_on은 최소 1개 이상의 신호를 포함해야 합니다.")
        invalid_notify_on = sorted(set(notify_on) - SUPPORTED_NOTIFY_SIGNALS)
        if invalid_notify_on:
            raise ValueError(
                "notify_on은 BUY, SELL만 포함할 수 있습니다: " + ", ".join(invalid_notify_on)
            )
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "notify_on", notify_on)


@dataclass(frozen=True)
class SmartMoneyAlertRecord:
    """symbol/timeframe별 마지막 Smart Money 알림 상태."""

    signal: str
    confidence: float
    sent_at: datetime


@dataclass(frozen=True)
class SmartMoneyAlertDecision:
    """알림 정책 평가 결과."""

    should_notify: bool
    reason: str


@dataclass(frozen=True)
class SmartMoneyAlertResult:
    """알림 전송 시도 결과."""

    should_notify: bool
    sent: bool
    reason: str
    provider: str
    message: str | None = None
    error: str | None = None
    state_saved: bool | None = None


class SmartMoneyAlertStateStore:
    """JSON 파일 기반 Smart Money 알림 상태 저장소."""

    def __init__(self, path: Path | str = DEFAULT_ALERT_STATE_PATH) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, SmartMoneyAlertRecord]:
        """상태 파일에서 Smart Money namespace만 읽는다."""
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            namespace = payload.get(STATE_NAMESPACE, {})
            if not isinstance(namespace, dict):
                logger.warning("Smart Money 알림 상태 namespace가 dict가 아니어서 무시합니다.")
                return {}
            return _decode_state(namespace)
        except Exception as exc:
            logger.warning("Smart Money 알림 상태 파일을 읽지 못했습니다: %s", exc)
            return {}

    def save(self, state: Mapping[str, SmartMoneyAlertRecord]) -> bool:
        """기존 JSON payload를 보존하면서 Smart Money namespace만 갱신한다."""
        payload: dict[str, Any] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception as exc:
                logger.warning("기존 알림 상태 파일을 갱신 전 읽지 못했습니다: %s", exc)
        payload[STATE_NAMESPACE] = _encode_state(state)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return True
        except Exception as exc:
            logger.warning("Smart Money 알림 상태 파일을 저장하지 못했습니다: %s", exc)
            return False


def evaluate_alert_policy(
    *,
    symbol: str,
    timeframe: str,
    signal: SmartMoneySignal,
    config: SmartMoneyAlertConfig,
    state: Mapping[str, SmartMoneyAlertRecord],
    now: datetime | None = None,
) -> SmartMoneyAlertDecision:
    """Smart Money 신호가 알림 대상인지 판단한다."""
    _validate_symbol(symbol)
    _validate_signal(signal)
    current_time = now or datetime.now()
    current_signal = signal.signal.strip().upper()
    state_key = build_alert_state_key(symbol, timeframe)

    if not config.enabled:
        return SmartMoneyAlertDecision(False, "disabled")
    if current_signal not in config.notify_on:
        return SmartMoneyAlertDecision(False, "signal_not_configured")
    if signal.confidence < config.min_confidence:
        return SmartMoneyAlertDecision(False, "below_min_confidence")

    previous = state.get(state_key)
    if previous is None:
        return SmartMoneyAlertDecision(True, "new_signal")
    if previous.signal.strip().upper() != current_signal:
        return SmartMoneyAlertDecision(True, "signal_changed")

    cooldown_until = previous.sent_at + timedelta(minutes=config.cooldown_minutes)
    if current_time < cooldown_until:
        return SmartMoneyAlertDecision(False, "cooldown")

    confidence_jump = signal.confidence - previous.confidence
    if config.repeat_on_confidence_jump and confidence_jump >= config.confidence_jump_threshold:
        return SmartMoneyAlertDecision(True, "confidence_jump")
    return SmartMoneyAlertDecision(False, "duplicate")


def dispatch_smart_money_alert(
    *,
    symbol: str,
    signal: SmartMoneySignal,
    timeframe: str = DEFAULT_TIMEFRAME,
    current_price: float | None = None,
    timeframe_summary: Sequence[str] | None = None,
    config: SmartMoneyAlertConfig | None = None,
    notifier: Any | None = None,
    state: MutableMapping[str, SmartMoneyAlertRecord] | None = None,
    state_store: SmartMoneyAlertStateStore | None = None,
    now: datetime | None = None,
) -> SmartMoneyAlertResult:
    """정책 평가 후 설정된 provider로 Smart Money 알림을 전송한다."""
    alert_config = config or SmartMoneyAlertConfig()
    current_time = now or datetime.now()
    active_state_store = state_store
    alert_state: MutableMapping[str, SmartMoneyAlertRecord]
    if state is None:
        active_state_store = state_store or SmartMoneyAlertStateStore()
        alert_state = active_state_store.load()
    else:
        alert_state = state
    decision = evaluate_alert_policy(
        symbol=symbol,
        timeframe=timeframe,
        signal=signal,
        config=alert_config,
        state=alert_state,
        now=current_time,
    )
    if not decision.should_notify:
        return SmartMoneyAlertResult(
            should_notify=False,
            sent=False,
            reason=decision.reason,
            provider=alert_config.provider,
        )

    message = format_smart_money_alert_message(
        symbol=symbol,
        signal=signal,
        current_price=current_price,
        timeframe_summary=timeframe_summary,
        now=current_time,
    )
    provider = notifier or _resolve_provider(alert_config.provider)
    if provider is None:
        logger.warning("Smart Money 알림 provider를 준비하지 못했습니다: %s", alert_config.provider)
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="provider_unavailable",
            provider=alert_config.provider,
            message=message,
        )

    try:
        sent = _send_with_provider(
            provider=provider,
            provider_name=alert_config.provider,
            symbol=symbol,
            action=signal.signal.strip().upper(),
            message=message,
        )
    except Exception as exc:
        logger.warning("Smart Money 알림 전송 중 provider 예외가 발생했습니다: %s", exc)
        _dispatch_signal_alert_failure_system_alert(
            provider=provider,
            provider_name=alert_config.provider,
            detail=f"provider_exception: {exc}",
            now=current_time,
        )
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="provider_exception",
            provider=alert_config.provider,
            message=message,
            error=str(exc),
        )

    if not sent:
        logger.warning("Smart Money 알림 provider가 실패를 반환했습니다: %s", alert_config.provider)
        _dispatch_signal_alert_failure_system_alert(
            provider=provider,
            provider_name=alert_config.provider,
            detail="provider_failed",
            now=current_time,
        )
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="provider_failed",
            provider=alert_config.provider,
            message=message,
        )

    alert_state[build_alert_state_key(symbol, timeframe)] = SmartMoneyAlertRecord(
        signal=signal.signal.strip().upper(),
        confidence=float(signal.confidence),
        sent_at=current_time,
    )
    state_saved: bool | None = None
    save_error: str | None = None
    if active_state_store is not None:
        state_saved = active_state_store.save(alert_state)
        if not state_saved:
            save_error = "state_save_failed"
    return SmartMoneyAlertResult(
        should_notify=True,
        sent=True,
        reason=decision.reason,
        provider=alert_config.provider,
        message=message,
        error=save_error,
        state_saved=state_saved,
    )


def dispatch_smart_money_system_alert(
    *,
    message: str,
    config: SmartMoneyAlertConfig | None = None,
    notifier: Any | None = None,
    now: datetime | None = None,
) -> SmartMoneyAlertResult:
    """데이터 수집/토큰 갱신 등 시스템 실패를 신호 알림과 분리해 전송한다."""
    alert_config = config or SmartMoneyAlertConfig()
    if not alert_config.enabled:
        return SmartMoneyAlertResult(
            should_notify=False,
            sent=False,
            reason="disabled",
            provider=alert_config.provider,
        )
    if not isinstance(message, str) or not message.strip():
        raise ValueError("system alert message는 비어 있지 않은 문자열이어야 합니다.")

    alert_message = format_smart_money_system_alert_message(
        message=message,
        now=now,
    )
    provider = notifier or _resolve_provider(alert_config.provider)
    if provider is None:
        logger.warning(
            "Smart Money system alert provider를 준비하지 못했습니다: %s", alert_config.provider
        )
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="provider_unavailable",
            provider=alert_config.provider,
            message=alert_message,
        )

    try:
        sent = _send_system_alert_with_provider(
            provider=provider,
            provider_name=alert_config.provider,
            message=alert_message,
        )
    except Exception as exc:
        logger.warning("Smart Money system alert 전송 중 provider 예외가 발생했습니다: %s", exc)
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="provider_exception",
            provider=alert_config.provider,
            message=alert_message,
            error=str(exc),
        )

    if not sent:
        logger.warning(
            "Smart Money system alert provider가 실패를 반환했습니다: %s", alert_config.provider
        )
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="provider_failed",
            provider=alert_config.provider,
            message=alert_message,
        )
    return SmartMoneyAlertResult(
        should_notify=True,
        sent=True,
        reason="system_alert_sent",
        provider=alert_config.provider,
        message=alert_message,
    )


def format_smart_money_alert_message(
    *,
    symbol: str,
    signal: SmartMoneySignal,
    current_price: float | None = None,
    timeframe_summary: Sequence[str] | None = None,
    now: datetime | None = None,
) -> str:
    """Kakao/Telegram 공용 Smart Money 알림 메시지를 만든다."""
    _validate_symbol(symbol)
    _validate_signal(signal)
    current_time = now or datetime.now()
    lines = [
        "[Smart Money Signal]",
        f"종목: {symbol.strip().upper()}",
        f"신호: {signal.signal.strip().upper()}",
        f"신뢰도: {signal.confidence:.0%}",
        f"현재가: {_format_optional_price(current_price)}",
        f"진입 후보: {_format_entry_zone(signal.entry_zone)}",
        f"무효화: {_format_optional_price(signal.invalidation_level)}",
        f"확인: {_format_summary(timeframe_summary)}",
        "근거:",
    ]
    reasons = list(signal.reasons[:3]) or ["제공된 Smart Money 신호 근거가 없습니다."]
    lines.extend(f"{index}. {reason}" for index, reason in enumerate(reasons, start=1))
    lines.extend(
        [
            f"시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "주의: 자동주문 아님, 판단 보조 알림입니다.",
        ]
    )
    return "\n".join(lines)


def format_smart_money_system_alert_message(
    *,
    message: str,
    now: datetime | None = None,
) -> str:
    """Kakao/Telegram 공용 Smart Money 시스템 알림 메시지를 만든다."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError("system alert message는 비어 있지 않은 문자열이어야 합니다.")
    current_time = now or datetime.now()
    return "\n".join(
        [
            "[Smart Money System Alert]",
            f"메시지: {message.strip()}",
            f"시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "주의: 매매 신호 알림과 분리된 시스템 알림입니다.",
        ]
    )


def build_alert_state_key(symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> str:
    """상태 저장에 사용할 symbol/timeframe key를 만든다."""
    _validate_symbol(symbol)
    normalized_timeframe = (timeframe or DEFAULT_TIMEFRAME).strip().lower()
    if not normalized_timeframe:
        normalized_timeframe = DEFAULT_TIMEFRAME
    return f"{symbol.strip().upper()}:{normalized_timeframe}"


def build_smart_money_alert_config(values: Mapping[str, Any] | None) -> SmartMoneyAlertConfig:
    """dict/YAML 설정값을 SmartMoneyAlertConfig로 변환한다."""
    if values is None:
        return SmartMoneyAlertConfig()
    if not isinstance(values, Mapping):
        raise ValueError("Smart Money 알림 설정은 mapping이어야 합니다.")
    notify_on = values.get("notify_on", ("BUY", "SELL"))
    notify_values: tuple[str, ...]
    if isinstance(notify_on, str) or notify_on is None:
        raise ValueError("notify_on은 문자열 시퀀스이어야 합니다.")
    else:
        try:
            notify_values = tuple(_normalize_notify_signal(item) for item in notify_on)
        except TypeError as exc:
            raise ValueError("notify_on은 문자열 시퀀스이어야 합니다.") from exc
    return SmartMoneyAlertConfig(
        enabled=bool(values.get("enabled", False)),
        provider=_string_setting(values, "provider", "kakao"),
        cooldown_minutes=int(values.get("cooldown_minutes", 30)),
        min_confidence=float(values.get("min_confidence", 0.60)),
        notify_on=notify_values,
        repeat_on_confidence_jump=bool(values.get("repeat_on_confidence_jump", True)),
        confidence_jump_threshold=float(values.get("confidence_jump_threshold", 0.15)),
    )


def _send_with_provider(
    *,
    provider: Any,
    provider_name: str,
    symbol: str,
    action: str,
    message: str,
) -> bool:
    """provider 종류에 맞는 전송 메서드를 호출한다."""
    if provider_name == "kakao":
        return bool(provider.send_signal_alert(symbol, action, message))
    if provider_name == "telegram":
        return bool(provider.send_message(message))
    raise ValueError(f"지원하지 않는 Smart Money 알림 provider입니다: {provider_name}")


def _normalize_notify_signal(value: object) -> str:
    """notify_on 항목을 검증하고 정규화한다."""
    if not isinstance(value, str):
        raise ValueError("notify_on은 문자열 시퀀스이어야 합니다.")
    return value.strip().upper()


def _string_setting(values: Mapping[str, Any], key: str, default: str) -> str:
    """문자열 설정값을 명시적으로 검증한다."""
    value = values.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key}는 문자열이어야 합니다.")
    return value


def _send_system_alert_with_provider(
    *,
    provider: Any,
    provider_name: str,
    message: str,
) -> bool:
    """provider 종류에 맞는 시스템 알림 전송 메서드를 호출한다."""
    if provider_name == "kakao":
        if not hasattr(provider, "send_error_alert"):
            raise ValueError("Kakao provider는 send_error_alert를 제공해야 합니다.")
        return bool(provider.send_error_alert(message))
    if provider_name == "telegram":
        return bool(provider.send_message(message))
    raise ValueError(f"지원하지 않는 Smart Money 알림 provider입니다: {provider_name}")


def _dispatch_signal_alert_failure_system_alert(
    *,
    provider: Any,
    provider_name: str,
    detail: str,
    now: datetime,
) -> None:
    """신호 알림 provider 실패를 별도 system alert로 시도하고 분석 흐름은 유지한다."""
    try:
        _send_system_alert_with_provider(
            provider=provider,
            provider_name=provider_name,
            message=format_smart_money_system_alert_message(
                message=f"Smart Money signal alert failed: {detail}",
                now=now,
            ),
        )
    except Exception as exc:
        logger.warning("Smart Money signal alert 실패 system alert 전송도 실패했습니다: %s", exc)


def _resolve_provider(provider_name: str) -> Any | None:
    """환경 설정 기반 기본 provider 인스턴스를 지연 로딩한다."""
    try:
        if provider_name == "kakao":
            module = import_module("src.utils.kakao_notifier")
            return module.get_kakao_notifier()
        if provider_name == "telegram":
            module = import_module("src.utils.telegram_notifier")
            return module.get_notifier()
    except Exception as exc:
        logger.warning("Smart Money 알림 provider 로딩에 실패했습니다: %s", exc)
        return None
    return None


def _encode_state(state: Mapping[str, SmartMoneyAlertRecord]) -> dict[str, dict[str, Any]]:
    """메모리 상태를 JSON 직렬화 가능한 dict로 변환한다."""
    encoded: dict[str, dict[str, Any]] = {}
    for key, record in state.items():
        encoded[key] = {
            "signal": record.signal,
            "confidence": float(record.confidence),
            "sent_at": record.sent_at.isoformat(),
        }
    return encoded


def _decode_state(payload: Mapping[str, Any]) -> dict[str, SmartMoneyAlertRecord]:
    """JSON payload를 SmartMoneyAlertRecord dict로 변환한다."""
    decoded: dict[str, SmartMoneyAlertRecord] = {}
    for key, raw_record in payload.items():
        if not isinstance(raw_record, Mapping):
            logger.warning("Smart Money 알림 상태 record가 dict가 아니어서 건너뜁니다: %s", key)
            continue
        try:
            decoded[str(key)] = SmartMoneyAlertRecord(
                signal=str(raw_record["signal"]),
                confidence=float(raw_record["confidence"]),
                sent_at=datetime.fromisoformat(str(raw_record["sent_at"])),
            )
        except Exception as exc:
            logger.warning("Smart Money 알림 상태 record를 해석하지 못했습니다: %s, %s", key, exc)
    return decoded


def _validate_symbol(symbol: str) -> None:
    """public API symbol 입력을 검증한다."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol은 비어 있지 않은 문자열이어야 합니다.")


def _validate_signal(signal: SmartMoneySignal) -> None:
    """public API signal 입력을 검증한다."""
    if signal is None:
        raise ValueError("signal은 None일 수 없습니다.")
    if not isinstance(signal.signal, str) or not signal.signal.strip():
        raise ValueError("signal.signal은 비어 있지 않은 문자열이어야 합니다.")
    if not 0.0 <= float(signal.confidence) <= 1.0:
        raise ValueError("signal.confidence는 0.0 이상 1.0 이하이어야 합니다.")


def _format_optional_price(value: float | None) -> str:
    """선택 가격 값을 메시지용 문자열로 변환한다."""
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_entry_zone(entry_zone: tuple[float, float] | None) -> str:
    """entry zone을 메시지용 문자열로 변환한다."""
    if entry_zone is None:
        return "N/A"
    return f"{entry_zone[0]:.2f} ~ {entry_zone[1]:.2f}"


def _format_summary(timeframe_summary: Sequence[str] | None) -> str:
    """timeframe 확인 요약을 메시지용 문자열로 변환한다."""
    if not timeframe_summary:
        return "N/A"
    return ", ".join(str(item) for item in timeframe_summary[:3])


__all__ = [
    "SmartMoneyAlertConfig",
    "SmartMoneyAlertDecision",
    "SmartMoneyAlertRecord",
    "SmartMoneyAlertResult",
    "SmartMoneyAlertStateStore",
    "build_alert_state_key",
    "build_smart_money_alert_config",
    "dispatch_smart_money_alert",
    "dispatch_smart_money_system_alert",
    "evaluate_alert_policy",
    "format_smart_money_alert_message",
    "format_smart_money_system_alert_message",
]
