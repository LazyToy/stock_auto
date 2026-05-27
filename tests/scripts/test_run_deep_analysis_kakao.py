from __future__ import annotations

from datetime import datetime

from scripts import run_deep_analysis_kakao as module


class FakeAnalyst:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def analyze_stock(self, symbol):
        self.calls.append(symbol)
        return self.payload


class FakeNotifier:
    def __init__(self, result=True):
        self.result = result
        self.messages = []

    def send_message(self, message):
        self.messages.append(message)
        return self.result


def test_run_deep_analysis_sends_kakao_summary_and_saves_report(tmp_path):
    analyst = FakeAnalyst(
        {
            "signal": "BUY",
            "confidence": 0.82,
            "reason": "Breakout held with improving volume.",
            "key_drivers": ["Trend reclaim", "Volume expansion"],
            "risk_factors": ["Market regime could weaken"],
            "analysis_sources": ["market", "technical", "news"],
        }
    )
    notifier = FakeNotifier()

    result = module.run_deep_analysis_kakao(
        "0183J0",
        analyst=analyst,
        notifier=notifier,
        output_dir=tmp_path,
        generated_at=datetime(2026, 5, 27, 9, 30),
        max_message_chars=500,
    )

    assert analyst.calls == ["0183J0"]
    assert result["sent"] is True
    assert result["message_count"] == 1
    assert result["report_path"].endswith("0183J0_deep_analysis_20260527_093000.json")
    assert (tmp_path / "0183J0_deep_analysis_20260527_093000.json").exists()
    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert "0183J0" in message
    assert "BUY" in message
    assert "82%" in message
    assert "Trend reclaim" in message
    assert "advisory only" in message


def test_run_deep_analysis_splits_long_kakao_messages(tmp_path):
    analyst = FakeAnalyst(
        {
            "signal": "HOLD",
            "confidence": 0.51,
            "reason": "x" * 260,
            "key_drivers": ["driver " + ("a" * 120)],
            "risk_factors": ["risk " + ("b" * 120)],
        }
    )
    notifier = FakeNotifier()

    result = module.run_deep_analysis_kakao(
        "AAPL",
        analyst=analyst,
        notifier=notifier,
        output_dir=tmp_path,
        generated_at=datetime(2026, 5, 27, 9, 30),
        max_message_chars=180,
    )

    assert result["sent"] is True
    assert result["message_count"] > 1
    assert len(notifier.messages) == result["message_count"]
    assert all(len(message) <= 180 for message in notifier.messages)
    assert notifier.messages[0].startswith("[1/")


def test_run_deep_analysis_keeps_repeated_reports_without_overwriting(tmp_path):
    analyst = FakeAnalyst({"signal": "HOLD", "confidence": 0.4, "reason": "first"})
    notifier = FakeNotifier()
    generated_at = datetime(2026, 5, 27, 9, 30)

    first = module.run_deep_analysis_kakao(
        "AAPL",
        analyst=analyst,
        notifier=notifier,
        output_dir=tmp_path,
        generated_at=generated_at,
        send=False,
    )
    second = module.run_deep_analysis_kakao(
        "AAPL",
        analyst=analyst,
        notifier=notifier,
        output_dir=tmp_path,
        generated_at=generated_at,
        send=False,
    )

    assert first["report_path"] != second["report_path"]
    assert first["report_path"].endswith("AAPL_deep_analysis_20260527_093000.json")
    assert second["report_path"].endswith("AAPL_deep_analysis_20260527_093000_2.json")
    assert notifier.messages == []


def test_run_deep_analysis_isolates_notifier_exceptions_and_redacts_error(tmp_path):
    class RaisingNotifier:
        def send_message(self, message):
            raise RuntimeError("failed with Bearer SECRET_TOKEN_123")

    analyst = FakeAnalyst({"signal": "BUY", "confidence": 0.7, "reason": "ok"})

    result = module.run_deep_analysis_kakao(
        "AAPL",
        analyst=analyst,
        notifier=RaisingNotifier(),
        output_dir=tmp_path,
        generated_at=datetime(2026, 5, 27, 9, 30),
        max_message_chars=500,
    )

    assert result["sent"] is False
    assert result["errors"]
    assert "SECRET_TOKEN_123" not in result["errors"][0]
    assert "Bearer <redacted>" in result["errors"][0]
