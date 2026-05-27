from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from scripts import run_smart_money_analysis as module
from src.analysis.smart_money.models import (
    MarketStructure,
    SignalConfig,
    SmartMoneyPatternConfig,
    SmartMoneySignal,
)
from src.analysis.smart_money.report import PatternSummary, TimeframePatternReport
from src.analysis.timeframes import MultiTimeframeDataset, Timeframe, TimeframeData


def _fixed_now() -> datetime:
    """리포트 생성 시각을 고정한다."""
    return datetime(2026, 4, 27, 9, 30, tzinfo=timezone.utc)


def _report(timeframe: str) -> TimeframePatternReport:
    """테스트용 timeframe 리포트를 만든다."""
    return TimeframePatternReport(
        timeframe=timeframe,
        latest_close=101.0,
        latest_bar_index=2,
        market_structure=MarketStructure.BULLISH,
        recent_swing_high=None,
        recent_swing_low=None,
        summary=PatternSummary(swing_count=2),
    )


def _dataset(symbol: str, market: str, exchange: str) -> MultiTimeframeDataset:
    """테스트용 전체 timeframe dataset을 만든다."""
    return MultiTimeframeDataset(
        symbol=symbol,
        market=market,
        exchange=exchange,
        timeframes={
            Timeframe.MINUTE_5: TimeframeData(
                timeframe=Timeframe.MINUTE_5,
                data=module._make_fixture_ohlcv("5min", 3, 100.0, 1.0),
                source="test",
            ),
            Timeframe.HOUR_1: TimeframeData(
                timeframe=Timeframe.HOUR_1,
                data=module._make_fixture_ohlcv("1h", 3, 100.0, 1.0),
                source="test",
            ),
            Timeframe.DAY_1: TimeframeData(
                timeframe=Timeframe.DAY_1,
                data=module._make_fixture_ohlcv("1D", 3, 100.0, 1.0),
                source="test",
            ),
        },
    )


def _patch_signal(monkeypatch, signal: SmartMoneySignal) -> None:
    """분석/신호 결합 함수를 지정 신호 반환으로 대체한다."""

    def fake_analyze_multi_timeframe_patterns(frames):
        return {"1d": _report("1d"), "1h": _report("1h"), "5m": _report("5m")}

    def fake_combine_multi_timeframe_signals(reports, config):
        return signal

    monkeypatch.setattr(
        module,
        "analyze_multi_timeframe_patterns",
        fake_analyze_multi_timeframe_patterns,
    )
    monkeypatch.setattr(
        module,
        "combine_multi_timeframe_signals",
        fake_combine_multi_timeframe_signals,
    )


def test_parse_symbols_splits_and_deduplicates_values() -> None:
    """CLI symbol 입력은 쉼표/줄바꿈을 지원하고 중복을 제거한다."""
    assert module.parse_symbols(" AAPL, msft\nAAPL,,005930 ") == ["AAPL", "MSFT", "005930"]


def test_parse_symbols_rejects_non_string_input() -> None:
    """비문자 symbol 입력은 명시적으로 거부한다."""
    try:
        module.parse_symbols(None)  # type: ignore[arg-type]
    except ValueError as exc:
        assert "symbols 입력은 문자열이어야 합니다." in str(exc)
    else:
        raise AssertionError("비문자 입력에서 ValueError가 발생해야 합니다.")


def test_fixture_json_report_is_created(tmp_path) -> None:
    """fixture 모드에서 네트워크 없이 JSON 리포트를 생성한다."""
    output = tmp_path / "smart_money.json"

    exit_code = module.main(
        [
            "--symbols",
            "AAPL,MSFT",
            "--market",
            "US",
            "--fixture",
            "--format",
            "json",
            "--output",
            str(output),
        ],
        clock=_fixed_now,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["generated_at"] == "2026-04-27T09:30:00+00:00"
    assert payload["summary"] == {
        "total_symbols": 2,
        "success_count": 2,
        "failure_count": 0,
    }
    assert [item["symbol"] for item in payload["results"]] == ["AAPL", "MSFT"]
    assert {"signal", "confidence", "reasons", "warnings", "timeframes"}.issubset(
        payload["results"][0]
    )


def test_fixture_markdown_report_is_created(tmp_path) -> None:
    """fixture 모드에서 Markdown 리포트를 생성한다."""
    output = tmp_path / "smart_money.md"

    exit_code = module.main(
        [
            "--symbols",
            "AAPL",
            "--market",
            "US",
            "--fixture",
            "--format",
            "markdown",
            "--output",
            str(output),
        ],
        clock=_fixed_now,
    )

    text = output.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "# Smart Money 분석 리포트" in text
    assert "AAPL" in text
    assert "signal" in text
    assert "confidence" in text
    assert "reasons" in text
    assert "warnings" in text


def test_buy_signal_serialization_keeps_entry_reasons_and_warnings(monkeypatch) -> None:
    """BUY 신호 리포트 직렬화에서 핵심 필드를 보존한다."""

    class FakeFetcher:
        def fetch_symbol(
            self,
            symbol: str,
            market: str = "KR",
            exchange: str = "NASD",
        ) -> MultiTimeframeDataset:
            return _dataset(symbol, market, exchange)

    _patch_signal(
        monkeypatch,
        SmartMoneySignal(
            signal="BUY",
            confidence=0.81,
            score=0.72,
            risk_level="LOW",
            entry_zone=(100.0, 102.0),
            invalidation_level=98.5,
            reasons=["일봉 구조가 상승 방향입니다."],
            warnings=["테스트 warning"],
        ),
    )

    payload = module.build_report_payload(
        ["AAPL"],
        market="US",
        exchange="NASD",
        generated_at=_fixed_now(),
        fetcher=FakeFetcher(),
    )
    result = payload["results"][0]
    markdown = module.render_markdown(payload)

    assert result["signal"] == "BUY"
    assert result["entry_zone"] == {"lower": 100.0, "upper": 102.0}
    assert result["invalidation"] == 98.5
    assert result["reasons"] == ["일봉 구조가 상승 방향입니다."]
    assert result["warnings"] == ["테스트 warning"]
    assert "| AAPL | BUY | 81.0% | 100.00 ~ 102.00 | 98.50 | 1 |" in markdown


def test_alert_dispatch_is_called_for_successful_signal_when_enabled(monkeypatch) -> None:
    """알림 설정이 켜져 있으면 성공 분석 결과에서 dispatch가 호출된다."""

    class FakeFetcher:
        def fetch_symbol(
            self,
            symbol: str,
            market: str = "KR",
            exchange: str = "NASD",
        ) -> MultiTimeframeDataset:
            return _dataset(symbol, market, exchange)

    calls = []

    def fake_dispatcher(**kwargs):
        calls.append(kwargs)
        return module.SmartMoneyAlertResult(
            should_notify=True,
            sent=True,
            reason="new_signal",
            provider="kakao",
        )

    _patch_signal(
        monkeypatch,
        SmartMoneySignal(
            signal="BUY",
            confidence=0.81,
            score=0.72,
            risk_level="LOW",
            reasons=["alert test"],
        ),
    )

    payload = module.build_report_payload(
        ["AAPL"],
        market="US",
        exchange="NASD",
        generated_at=_fixed_now(),
        fetcher=FakeFetcher(),
        alert_config=module.SmartMoneyAlertConfig(enabled=True, provider="kakao"),
        alert_dispatcher=fake_dispatcher,
    )

    assert len(calls) == 1
    assert calls[0]["symbol"] == "AAPL"
    assert calls[0]["signal"].signal == "BUY"
    assert calls[0]["config"].enabled is True
    assert payload["results"][0]["alert"] == {
        "should_notify": True,
        "sent": True,
        "reason": "new_signal",
        "provider": "kakao",
        "error": None,
        "state_saved": None,
    }


def test_build_report_payload_forwards_signal_and_pattern_config(monkeypatch) -> None:
    """CLI 리포트 생성은 YAML에서 만든 signal/pattern config를 분석 파이프라인에 전달한다."""

    class FakeFetcher:
        def fetch_symbol(
            self,
            symbol: str,
            market: str = "KR",
            exchange: str = "NASD",
        ) -> MultiTimeframeDataset:
            return _dataset(symbol, market, exchange)

    calls = {}
    signal_config = SignalConfig(buy_threshold=0.62)
    pattern_config = SmartMoneyPatternConfig(fvg_min_gap_pct=0.50)

    def fake_analyze_multi_timeframe_patterns(frames, pattern_config=None):
        calls["pattern_config"] = pattern_config
        return {"1d": _report("1d"), "1h": _report("1h"), "5m": _report("5m")}

    def fake_combine_multi_timeframe_signals(reports, config):
        calls["signal_config"] = config
        return SmartMoneySignal(signal="HOLD", confidence=0.0, score=0.0, risk_level="HIGH")

    monkeypatch.setattr(
        module,
        "analyze_multi_timeframe_patterns",
        fake_analyze_multi_timeframe_patterns,
    )
    monkeypatch.setattr(
        module,
        "combine_multi_timeframe_signals",
        fake_combine_multi_timeframe_signals,
    )

    module.build_report_payload(
        ["AAPL"],
        market="US",
        exchange="NASD",
        generated_at=_fixed_now(),
        fetcher=FakeFetcher(),
        config=signal_config,
        pattern_config=pattern_config,
    )

    assert calls["signal_config"] is signal_config
    assert calls["pattern_config"] is pattern_config


def test_fetch_failure_dispatches_system_alert_when_enabled() -> None:
    """데이터 수집 실패는 signal alert와 별도 system alert로 전송된다."""

    class FailingFetcher:
        def fetch_symbol(
            self,
            symbol: str,
            market: str = "KR",
            exchange: str = "NASD",
        ) -> MultiTimeframeDataset:
            raise RuntimeError("API rate limit")

    calls = []

    def fake_system_dispatcher(**kwargs):
        calls.append(kwargs)
        return module.SmartMoneyAlertResult(
            should_notify=True,
            sent=True,
            reason="system_alert_sent",
            provider="kakao",
        )

    payload = module.build_report_payload(
        ["AAPL"],
        market="US",
        exchange="NASD",
        generated_at=_fixed_now(),
        fetcher=FailingFetcher(),
        alert_config=module.SmartMoneyAlertConfig(enabled=True, provider="kakao"),
        system_alert_dispatcher=fake_system_dispatcher,
    )

    result = payload["results"][0]
    assert len(calls) == 1
    assert "AAPL data_fetch: API rate limit" == calls[0]["message"]
    assert result["status"] == "error"
    assert result["alert"] is None
    assert result["system_alert"] == {
        "should_notify": True,
        "sent": True,
        "reason": "system_alert_sent",
        "provider": "kakao",
        "error": None,
        "state_saved": None,
    }


def test_sell_signal_serialization_keeps_entry_reasons_and_warnings(monkeypatch) -> None:
    """SELL 신호 리포트 직렬화에서 핵심 필드를 보존한다."""

    class FakeFetcher:
        def fetch_symbol(
            self,
            symbol: str,
            market: str = "KR",
            exchange: str = "NASD",
        ) -> MultiTimeframeDataset:
            return _dataset(symbol, market, exchange)

    _patch_signal(
        monkeypatch,
        SmartMoneySignal(
            signal="SELL",
            confidence=0.76,
            score=-0.68,
            risk_level="MEDIUM",
            entry_zone=(110.0, 112.0),
            invalidation_level=114.5,
            reasons=["일봉 구조가 하락 방향입니다."],
            warnings=["SELL 테스트 warning"],
        ),
    )

    payload = module.build_report_payload(
        ["MSFT"],
        market="US",
        exchange="NASD",
        generated_at=_fixed_now(),
        fetcher=FakeFetcher(),
    )
    result = payload["results"][0]
    markdown = module.render_markdown(payload)

    assert result["signal"] == "SELL"
    assert result["entry_zone"] == {"lower": 110.0, "upper": 112.0}
    assert result["invalidation"] == 114.5
    assert result["reasons"] == ["일봉 구조가 하락 방향입니다."]
    assert result["warnings"] == ["SELL 테스트 warning"]
    assert "| MSFT | SELL | 76.0% | 110.00 ~ 112.00 | 114.50 | 1 |" in markdown


def test_no_network_mode_uses_fixture_fetcher(tmp_path) -> None:
    """--no-network는 외부 호출 없이 fixture fetcher로 리포트를 생성한다."""
    output = tmp_path / "smart_money_no_network.json"

    exit_code = module.main(
        [
            "--symbols",
            "AAPL",
            "--market",
            "US",
            "--no-network",
            "--format",
            "json",
            "--output",
            str(output),
        ],
        clock=_fixed_now,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["results"][0]["symbol"] == "AAPL"


def test_partial_symbol_failure_is_recorded_in_warnings(tmp_path) -> None:
    """일부 timeframe 실패는 종목 실패가 아니라 warnings에 기록한다."""
    output = tmp_path / "smart_money_partial.json"

    exit_code = module.main(
        [
            "--symbols",
            "PARTIAL,AAPL",
            "--market",
            "US",
            "--fixture",
            "--format",
            "json",
            "--output",
            str(output),
        ],
        clock=_fixed_now,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    partial = payload["results"][0]
    assert exit_code == 0
    assert partial["symbol"] == "PARTIAL"
    assert partial["status"] == "success"
    assert "1d: fixture daily failure" in partial["warnings"]
    assert partial["timeframes"]["1d"] == {
        "status": "error",
        "error": "fixture daily failure",
    }


def test_all_symbol_failures_return_exit_code_1(tmp_path) -> None:
    """모든 종목이 실패하면 리포트는 남기고 exit code 1을 반환한다."""
    output = tmp_path / "smart_money_failed.json"

    exit_code = module.main(
        [
            "--symbols",
            "FAIL_ONE,FAIL_TWO",
            "--market",
            "US",
            "--fixture",
            "--format",
            "json",
            "--output",
            str(output),
        ],
        clock=_fixed_now,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["summary"]["failure_count"] == 2
    assert all(item["status"] == "error" for item in payload["results"])


def test_script_file_can_run_directly_from_project_root(tmp_path) -> None:
    """PR 수동 검증 명령처럼 script 파일 경로로 직접 실행할 수 있다."""
    output = tmp_path / "smart_money_direct.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_smart_money_analysis.py",
            "--symbols",
            "AAPL",
            "--market",
            "US",
            "--fixture",
            "--format",
            "markdown",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "# Smart Money 분석 리포트" in output.read_text(encoding="utf-8")
