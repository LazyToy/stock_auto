"""PR-13: Smart Money 알림 정책 테스트."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.analysis.smart_money.models import SmartMoneySignal


class FakeKakaoNotifier:
    """카카오 notifier 호출 내용을 기록하는 테스트 대역."""

    def __init__(
        self,
        *,
        should_raise: bool = False,
        result: bool = True,
        error_result: bool | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.error_calls: list[str] = []
        self.should_raise = should_raise
        self.result = result
        self.error_result = result if error_result is None else error_result

    def send_signal_alert(self, symbol: str, action: str, reason: str) -> bool:
        """Smart Money 알림 호출을 기록한다."""
        if self.should_raise:
            raise RuntimeError("notifier failed")
        self.calls.append((symbol, action, reason))
        return self.result

    def send_error_alert(self, error_message: str) -> bool:
        """시스템 오류 알림 호출을 기록한다."""
        if self.should_raise:
            raise RuntimeError("notifier failed")
        self.error_calls.append(error_message)
        return self.error_result


class FakeTelegramNotifier:
    """Telegram notifier 호출 내용을 기록하는 테스트 대역."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def send_message(self, message: str) -> bool:
        """Telegram 메시지 호출을 기록한다."""
        self.calls.append(message)
        return True


def _signal(
    signal: str,
    confidence: float,
    *,
    reasons: list[str] | None = None,
    entry_zone: tuple[float, float] | None = (181.8, 183.1),
    invalidation_level: float | None = 178.5,
) -> SmartMoneySignal:
    """테스트용 SmartMoneySignal을 만든다."""
    return SmartMoneySignal(
        signal=signal,
        confidence=confidence,
        score=confidence,
        risk_level="LOW",
        entry_zone=entry_zone,
        invalidation_level=invalidation_level,
        reasons=list(reasons or ["daily BULLISH", "hourly FVG touched", "5m CHOCH"]),
        warnings=[],
        contributions=[],
    )


class TestSmartMoneyAlertPolicy(unittest.TestCase):
    """알림 발생 여부 판단 정책을 검증한다."""

    def test_threshold_below_minimum_does_not_notify(self) -> None:
        """신뢰도가 기준 미만이면 알림을 만들지 않는다."""
        from src.analysis.smart_money.alerts import SmartMoneyAlertConfig, evaluate_alert_policy

        decision = evaluate_alert_policy(
            symbol="AAPL",
            timeframe="multi",
            signal=_signal("BUY", 0.59),
            config=SmartMoneyAlertConfig(enabled=True, min_confidence=0.60),
            state={},
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertFalse(decision.should_notify)
        self.assertEqual(decision.reason, "below_min_confidence")

    def test_same_signal_inside_cooldown_does_not_notify(self) -> None:
        """동일 신호는 cooldown 시간 안에서 중복 발송하지 않는다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            SmartMoneyAlertRecord,
            evaluate_alert_policy,
        )

        now = datetime(2026, 4, 23, 9, 35)
        state = {
            "AAPL:multi": SmartMoneyAlertRecord(
                signal="BUY",
                confidence=0.70,
                sent_at=now - timedelta(minutes=10),
            )
        }

        decision = evaluate_alert_policy(
            symbol="AAPL",
            timeframe="multi",
            signal=_signal("BUY", 0.72),
            config=SmartMoneyAlertConfig(enabled=True, cooldown_minutes=30),
            state=state,
            now=now,
        )

        self.assertFalse(decision.should_notify)
        self.assertEqual(decision.reason, "cooldown")

    def test_signal_change_notifies(self) -> None:
        """HOLD 이후 BUY/SELL 전환은 알림 대상이다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            SmartMoneyAlertRecord,
            evaluate_alert_policy,
        )

        now = datetime(2026, 4, 23, 9, 35)
        state = {
            "AAPL:multi": SmartMoneyAlertRecord(
                signal="HOLD",
                confidence=0.40,
                sent_at=now - timedelta(minutes=5),
            )
        }

        decision = evaluate_alert_policy(
            symbol="AAPL",
            timeframe="multi",
            signal=_signal("SELL", 0.68),
            config=SmartMoneyAlertConfig(enabled=True),
            state=state,
            now=now,
        )

        self.assertTrue(decision.should_notify)
        self.assertEqual(decision.reason, "signal_changed")

    def test_config_rejects_invalid_notify_on_value(self) -> None:
        """notify_on 오타는 설정 생성 시 명시적으로 실패한다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            build_smart_money_alert_config,
        )

        with self.assertRaisesRegex(ValueError, "notify_on은 BUY, SELL만 포함할 수 있습니다"):
            SmartMoneyAlertConfig(enabled=True, notify_on=("BOGUS",))
        with self.assertRaisesRegex(ValueError, "provider는 문자열이어야 합니다"):
            SmartMoneyAlertConfig(enabled=True, provider=None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "notify_on은 문자열 시퀀스이어야 합니다"):
            SmartMoneyAlertConfig(enabled=True, notify_on=None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "notify_on은 문자열 시퀀스이어야 합니다"):
            build_smart_money_alert_config({"notify_on": None})

    def test_all_required_signal_changes_notify(self) -> None:
        """명세의 주요 BUY/SELL 전환은 모두 알림 대상이다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            SmartMoneyAlertRecord,
            evaluate_alert_policy,
        )

        now = datetime(2026, 4, 23, 9, 35)
        transitions = [
            ("HOLD", "BUY"),
            ("HOLD", "SELL"),
            ("BUY", "SELL"),
            ("SELL", "BUY"),
        ]
        for previous_signal, current_signal in transitions:
            with self.subTest(previous_signal=previous_signal, current_signal=current_signal):
                state = {
                    "AAPL:multi": SmartMoneyAlertRecord(
                        signal=previous_signal,
                        confidence=0.40,
                        sent_at=now - timedelta(minutes=5),
                    )
                }
                decision = evaluate_alert_policy(
                    symbol="AAPL",
                    timeframe="multi",
                    signal=_signal(current_signal, 0.68),
                    config=SmartMoneyAlertConfig(enabled=True),
                    state=state,
                    now=now,
                )

                self.assertTrue(decision.should_notify)
                self.assertEqual(decision.reason, "signal_changed")

    def test_confidence_jump_can_notify_once_after_cooldown(self) -> None:
        """동일 신호라도 cooldown 이후 신뢰도 상승폭이 충분하면 재알림한다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            SmartMoneyAlertRecord,
            evaluate_alert_policy,
        )

        now = datetime(2026, 4, 23, 9, 35)
        state = {
            "AAPL:multi": SmartMoneyAlertRecord(
                signal="BUY",
                confidence=0.60,
                sent_at=now - timedelta(minutes=31),
            )
        }

        decision = evaluate_alert_policy(
            symbol="AAPL",
            timeframe="multi",
            signal=_signal("BUY", 0.76),
            config=SmartMoneyAlertConfig(
                enabled=True,
                repeat_on_confidence_jump=True,
                confidence_jump_threshold=0.15,
            ),
            state=state,
            now=now,
        )

        self.assertTrue(decision.should_notify)
        self.assertEqual(decision.reason, "confidence_jump")


class TestSmartMoneyAlertDispatch(unittest.TestCase):
    """provider 호출, 상태 저장, 실패 격리를 검증한다."""

    def test_kakao_provider_uses_send_signal_alert_and_message_contains_required_fields(
        self,
    ) -> None:
        """kakao provider는 send_signal_alert를 호출하고 필수 메시지 필드를 포함한다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            dispatch_smart_money_alert,
        )

        notifier = FakeKakaoNotifier()
        result = dispatch_smart_money_alert(
            symbol="AAPL",
            signal=_signal("BUY", 0.68),
            current_price=182.4,
            timeframe_summary=["daily BULLISH", "hourly FVG touched", "5m CHOCH"],
            config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
            notifier=notifier,
            state={},
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertTrue(result.sent)
        self.assertEqual(len(notifier.calls), 1)
        symbol, action, message = notifier.calls[0]
        self.assertEqual(symbol, "AAPL")
        self.assertEqual(action, "BUY")
        self.assertIn("[Smart Money Signal]", message)
        self.assertIn("종목: AAPL", message)
        self.assertIn("신호: BUY", message)
        self.assertIn("신뢰도: 68%", message)
        self.assertIn("현재가: 182.40", message)
        self.assertIn("자동주문 아님", message)

    def test_telegram_provider_uses_send_message(self) -> None:
        """telegram provider는 send_message를 호출한다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            dispatch_smart_money_alert,
        )

        notifier = FakeTelegramNotifier()
        result = dispatch_smart_money_alert(
            symbol="AAPL",
            signal=_signal("SELL", 0.70),
            config=SmartMoneyAlertConfig(enabled=True, provider="telegram"),
            notifier=notifier,
            state={},
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertTrue(result.sent)
        self.assertEqual(len(notifier.calls), 1)
        self.assertIn("신호: SELL", notifier.calls[0])

    def test_notifier_exception_does_not_raise(self) -> None:
        """notifier 예외는 분석 흐름을 중단시키지 않고 실패 결과로 반환된다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            dispatch_smart_money_alert,
        )

        result = dispatch_smart_money_alert(
            symbol="AAPL",
            signal=_signal("BUY", 0.68),
            config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
            notifier=FakeKakaoNotifier(should_raise=True),
            state={},
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertFalse(result.sent)
        self.assertEqual(result.reason, "provider_exception")

    def test_provider_false_result_attempts_separate_system_alert(self) -> None:
        """provider 실패 반환은 별도 system alert 전송을 시도한다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            dispatch_smart_money_alert,
        )

        notifier = FakeKakaoNotifier(result=False, error_result=True)
        result = dispatch_smart_money_alert(
            symbol="AAPL",
            signal=_signal("BUY", 0.68),
            config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
            notifier=notifier,
            state={},
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertFalse(result.sent)
        self.assertEqual(result.reason, "provider_failed")
        self.assertEqual(len(notifier.calls), 1)
        self.assertEqual(len(notifier.error_calls), 1)
        self.assertIn("Smart Money signal alert failed", notifier.error_calls[0])

    def test_file_state_store_round_trips_namespace(self) -> None:
        """상태 파일은 smart_money_alerts namespace 아래에 저장된다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            SmartMoneyAlertStateStore,
            dispatch_smart_money_alert,
        )

        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "smart_money_alert_state.json"
            store = SmartMoneyAlertStateStore(state_path)
            result = dispatch_smart_money_alert(
                symbol="AAPL",
                signal=_signal("BUY", 0.68),
                config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
                notifier=FakeKakaoNotifier(),
                state_store=store,
                now=datetime(2026, 4, 23, 9, 35),
            )

            self.assertTrue(result.sent)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("smart_money_alerts", payload)
            self.assertIn("AAPL:multi", payload["smart_money_alerts"])

    def test_default_state_store_blocks_second_dispatch_inside_cooldown(self) -> None:
        """기본 state store 경로도 성공 알림 후 상태를 저장해 중복 발송을 막는다."""
        import src.analysis.smart_money.alerts as alerts
        from src.analysis.smart_money.alerts import SmartMoneyAlertConfig, SmartMoneyAlertStateStore

        with TemporaryDirectory() as temp_dir:
            store = SmartMoneyAlertStateStore(Path(temp_dir) / "smart_money_alert_state.json")
            notifier = FakeKakaoNotifier()
            with patch.object(alerts, "SmartMoneyAlertStateStore", return_value=store):
                first = alerts.dispatch_smart_money_alert(
                    symbol="AAPL",
                    signal=_signal("BUY", 0.68),
                    config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
                    notifier=notifier,
                    now=datetime(2026, 4, 23, 9, 35),
                )
                second = alerts.dispatch_smart_money_alert(
                    symbol="AAPL",
                    signal=_signal("BUY", 0.69),
                    config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
                    notifier=notifier,
                    now=datetime(2026, 4, 23, 9, 45),
                )

            self.assertTrue(first.sent)
            self.assertFalse(second.sent)
            self.assertEqual(second.reason, "cooldown")
            self.assertEqual(len(notifier.calls), 1)

    def test_state_store_save_failure_is_reported(self) -> None:
        """상태 저장 실패는 발송 결과의 error/state_saved로 노출된다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            dispatch_smart_money_alert,
        )

        class FailingStateStore:
            def load(self):
                return {}

            def save(self, state):
                return False

        result = dispatch_smart_money_alert(
            symbol="AAPL",
            signal=_signal("BUY", 0.68),
            config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
            notifier=FakeKakaoNotifier(),
            state_store=FailingStateStore(),  # type: ignore[arg-type]
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertTrue(result.sent)
        self.assertFalse(result.state_saved)
        self.assertEqual(result.error, "state_save_failed")

    def test_system_alert_uses_kakao_error_alert(self) -> None:
        """시스템 알림은 매매 신호 알림과 분리된 send_error_alert를 호출한다."""
        from src.analysis.smart_money.alerts import (
            SmartMoneyAlertConfig,
            dispatch_smart_money_system_alert,
        )

        notifier = FakeKakaoNotifier()
        result = dispatch_smart_money_system_alert(
            message="AAPL data fetch failed: rate limit",
            config=SmartMoneyAlertConfig(enabled=True, provider="kakao"),
            notifier=notifier,
            now=datetime(2026, 4, 23, 9, 35),
        )

        self.assertTrue(result.sent)
        self.assertEqual(result.reason, "system_alert_sent")
        self.assertEqual(len(notifier.error_calls), 1)
        self.assertEqual(notifier.calls, [])
        self.assertIn("[Smart Money System Alert]", notifier.error_calls[0])
        self.assertIn("rate limit", notifier.error_calls[0])


class TestSmartMoneyAlertPackageImport(unittest.TestCase):
    """smart_money 패키지 public API export를 검증한다."""

    def test_alert_public_api_import_succeeds(self) -> None:
        """src.analysis.smart_money에서 alert 관련 public API를 import할 수 있다."""
        from src.analysis.smart_money import (  # noqa: F401
            SmartMoneyAlertConfig,
            SmartMoneyAlertStateStore,
            dispatch_smart_money_alert,
            dispatch_smart_money_system_alert,
            evaluate_alert_policy,
            format_smart_money_alert_message,
            format_smart_money_system_alert_message,
        )


if __name__ == "__main__":
    unittest.main()
