from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.smart_money.models import MarketStructure, SmartMoneySignal
from src.analysis.smart_money.report import PatternSummary, TimeframePatternReport


def _report(timeframe: str, structure: MarketStructure) -> TimeframePatternReport:
    return TimeframePatternReport(
        timeframe=timeframe,
        latest_close=100.0,
        latest_bar_index=2,
        market_structure=structure,
        recent_swing_high=None,
        recent_swing_low=None,
        summary=PatternSummary(
            swing_count=2,
            structure_break_count=1,
            open_fvg_count=1,
            fresh_order_block_count=1,
        ),
        warnings=[],
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000, 1100, 1200],
        },
        index=pd.date_range("2024-01-02", periods=3, freq="1D"),
    )


def test_parse_symbol_input_splits_commas_and_removes_blank_values() -> None:
    from dashboard.components.smart_money_tab import parse_symbol_input

    assert parse_symbol_input(" AAPL, MSFT,\n005930 ,, AAPL ") == ["AAPL", "MSFT", "005930"]


def test_run_smart_money_batch_skips_fetcher_for_empty_symbol_input() -> None:
    from dashboard.components.smart_money_tab import run_smart_money_batch

    class FakeFetcher:
        def fetch_symbol(self, symbol: str, market: str = "KR", exchange: str = "NASD"):
            raise AssertionError("빈 입력에서는 fetch_symbol을 호출하면 안 됩니다.")

    assert run_smart_money_batch("", market="KR", exchange="NASD", fetcher=FakeFetcher()) == []


def test_build_result_rows_contains_required_dashboard_columns() -> None:
    from dashboard.components.smart_money_tab import SmartMoneySymbolAnalysis, build_result_rows

    signal = SmartMoneySignal(
        signal="BUY",
        confidence=0.72,
        score=0.61,
        risk_level="MEDIUM",
        entry_zone=(101.0, 103.0),
        invalidation_level=99.5,
        reasons=["일봉 구조가 상승 방향을 유지합니다.", "1시간봉 setup 확인"],
    )
    result = SmartMoneySymbolAnalysis(
        symbol="AAPL",
        market="US",
        exchange="NASD",
        frames={"1d": _frame(), "1h": _frame(), "5m": _frame()},
        reports={
            "1d": _report("1d", MarketStructure.BULLISH),
            "1h": _report("1h", MarketStructure.RANGE),
            "5m": _report("5m", MarketStructure.BULLISH),
        },
        signal=signal,
    )

    rows = build_result_rows([result])

    assert rows == [
        {
            "symbol": "AAPL",
            "signal": "BUY",
            "confidence": "72.0%",
            "daily structure": "BULLISH",
            "1h setup": "FVG 1 / OB 1",
            "5m trigger": "구조돌파 1 / 스윕 0 / 캔들패턴 0",
            "entry zone": "101.00 ~ 103.00",
            "invalidation": "99.50",
            "주요 reason": "일봉 구조가 상승 방향을 유지합니다.",
        }
    ]


def test_failed_timeframe_warning_is_preserved_in_analysis_result() -> None:
    from dashboard.components.smart_money_tab import SmartMoneySymbolAnalysis, collect_warnings

    result = SmartMoneySymbolAnalysis(
        symbol="AAPL",
        market="US",
        exchange="NASD",
        timeframe_errors={"1d": "yfinance 실패"},
        reports={"5m": _report("5m", MarketStructure.RANGE)},
        signal=SmartMoneySignal("HOLD", 0.0, 0.0, "HIGH", warnings=["daily 누락"]),
    )

    assert collect_warnings(result) == ["1d: yfinance 실패", "daily 누락"]


def test_build_selected_chart_passes_matching_frame_report_and_signal() -> None:
    from dashboard.components.smart_money_tab import SmartMoneySymbolAnalysis, build_selected_chart

    calls = []
    signal = SmartMoneySignal("HOLD", 0.2, 0.0, "HIGH")
    frame = _frame()
    report = _report("1h", MarketStructure.RANGE)

    def fake_builder(df, report_arg, signal_arg):
        calls.append((df, report_arg, signal_arg))
        return "figure"

    result = SmartMoneySymbolAnalysis(
        symbol="AAPL",
        market="US",
        exchange="NASD",
        frames={"1h": frame},
        reports={"1h": report},
        signal=signal,
    )

    assert build_selected_chart(result, "1h", figure_builder=fake_builder) == "figure"
    assert calls == [(frame, report, signal)]


def test_run_smart_money_batch_dispatches_alert_when_enabled(monkeypatch) -> None:
    import dashboard.components.smart_money_tab as module
    from src.analysis.timeframes import MultiTimeframeDataset, Timeframe, TimeframeData

    class FakeFetcher:
        def fetch_symbol(self, symbol: str, market: str = "KR", exchange: str = "NASD"):
            return MultiTimeframeDataset(
                symbol=symbol,
                market=market,
                exchange=exchange,
                timeframes={
                    Timeframe.MINUTE_5: TimeframeData(Timeframe.MINUTE_5, data=_frame()),
                    Timeframe.HOUR_1: TimeframeData(Timeframe.HOUR_1, data=_frame()),
                    Timeframe.DAY_1: TimeframeData(Timeframe.DAY_1, data=_frame()),
                },
            )

    calls = []

    def fake_analyze_multi_timeframe_patterns(frames):
        return {
            "5m": _report("5m", MarketStructure.BULLISH),
            "1h": _report("1h", MarketStructure.BULLISH),
            "1d": _report("1d", MarketStructure.BULLISH),
        }

    def fake_combine_multi_timeframe_signals(reports, config):
        return SmartMoneySignal("BUY", 0.8, 0.7, "LOW", reasons=["alert test"])

    def fake_dispatcher(**kwargs):
        calls.append(kwargs)
        return module.SmartMoneyAlertResult(
            should_notify=True,
            sent=True,
            reason="new_signal",
            provider="kakao",
        )

    monkeypatch.setattr(
        module,
        "analyze_multi_timeframe_patterns",
        fake_analyze_multi_timeframe_patterns,
    )
    monkeypatch.setattr(
        module, "combine_multi_timeframe_signals", fake_combine_multi_timeframe_signals
    )

    results = module.run_smart_money_batch(
        "AAPL",
        market="US",
        exchange="NASD",
        fetcher=FakeFetcher(),
        alert_config=module.SmartMoneyAlertConfig(enabled=True, provider="kakao"),
        alert_dispatcher=fake_dispatcher,
    )

    assert len(results) == 1
    assert len(calls) == 1
    assert calls[0]["symbol"] == "AAPL"
    assert calls[0]["signal"].signal == "BUY"


def test_run_smart_money_batch_dispatches_system_alert_on_fetch_failure() -> None:
    import dashboard.components.smart_money_tab as module

    class FailingFetcher:
        def fetch_symbol(self, symbol: str, market: str = "KR", exchange: str = "NASD"):
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

    results = module.run_smart_money_batch(
        "AAPL",
        market="US",
        exchange="NASD",
        fetcher=FailingFetcher(),
        alert_config=module.SmartMoneyAlertConfig(enabled=True, provider="kakao"),
        system_alert_dispatcher=fake_system_dispatcher,
    )

    assert len(results) == 1
    assert len(calls) == 1
    assert calls[0]["message"] == "AAPL data_fetch: API rate limit"
    assert results[0].error == "데이터 수집 실패: API rate limit"


class _SmartMoneyTabFakeStreamlit:
    def __init__(self, market: str) -> None:
        self.market = market
        self.session_state = {}
        self.selectbox_calls = []
        self.caption_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def header(self, message):
        pass

    def columns(self, spec):
        return [self, self, self]

    def text_area(self, *args, **kwargs):
        return "005930"

    def selectbox(self, label, options, **kwargs):
        self.selectbox_calls.append((label, list(options), kwargs))
        if label == "시장":
            return self.market
        return options[0]

    def caption(self, message):
        self.caption_calls.append(message)

    def button(self, *args, **kwargs):
        return False

    def info(self, message):
        pass


def test_render_smart_money_tab_hides_exchange_selector_for_kr_market() -> None:
    from dashboard.components.smart_money_tab import render_smart_money_tab

    fake_st = _SmartMoneyTabFakeStreamlit(market="KR")

    render_smart_money_tab(st_api=fake_st)

    assert [call[0] for call in fake_st.selectbox_calls] == ["시장"]
    assert fake_st.caption_calls == ["KR 시장은 KRX 기준으로 분석합니다."]


def test_render_smart_money_tab_shows_us_exchange_options_for_us_market() -> None:
    from dashboard.components.smart_money_tab import render_smart_money_tab

    fake_st = _SmartMoneyTabFakeStreamlit(market="US")

    render_smart_money_tab(st_api=fake_st)

    assert [call[0] for call in fake_st.selectbox_calls] == ["시장", "거래소"]
    assert fake_st.selectbox_calls[1][1] == ["NASD", "NYSE", "AMEX"]
    assert fake_st.caption_calls == []


def test_render_detail_warns_when_chart_builder_fails(monkeypatch) -> None:
    import dashboard.components.smart_money_tab as module
    from dashboard.components.smart_money_tab import SmartMoneySymbolAnalysis

    class FakeStreamlit:
        def __init__(self) -> None:
            self.warning_calls = []
            self.markdown_calls = []
            self.subheader_calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def subheader(self, message):
            self.subheader_calls.append(message)

        def tabs(self, labels):
            return [self for _ in labels]

        def warning(self, message):
            self.warning_calls.append(message)

        def plotly_chart(self, figure, **kwargs):
            raise AssertionError("차트 생성 실패 시 plotly_chart를 호출하면 안 됩니다.")

        def markdown(self, message):
            self.markdown_calls.append(message)

    def failing_chart_builder(result, timeframe):
        if timeframe == "1h":
            raise RuntimeError("차트 생성 실패")
        return None

    result = SmartMoneySymbolAnalysis(
        symbol="AAPL",
        market="US",
        exchange="NASD",
        frames={"1h": _frame()},
        reports={"1h": _report("1h", MarketStructure.RANGE)},
        signal=SmartMoneySignal("HOLD", 0.2, 0.0, "HIGH"),
    )
    fake_st = FakeStreamlit()
    monkeypatch.setattr(module, "build_selected_chart", failing_chart_builder)

    module._render_detail(result, st_api=fake_st)

    assert "1시간봉 차트 생성 실패: 차트 생성 실패" in fake_st.warning_calls
    assert fake_st.markdown_calls


def test_dashboard_app_wires_smart_money_tab() -> None:
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "from dashboard.components.smart_money_tab import render_smart_money_tab" in text
    assert "Smart Money" in text
    assert "render_smart_money_tab()" in text
