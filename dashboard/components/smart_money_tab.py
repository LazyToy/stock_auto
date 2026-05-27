from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]
import streamlit as st

from src.analysis.smart_money import (
    SignalConfig,
    SmartMoneyAlertConfig,
    SmartMoneyAlertResult,
    SmartMoneySignal,
    TimeframePatternReport,
    analyze_multi_timeframe_patterns,
    build_smart_money_alert_config,
    build_smart_money_figure,
    combine_multi_timeframe_signals,
    dispatch_smart_money_alert,
    dispatch_smart_money_system_alert,
)
from src.analysis.timeframes import MultiTimeframeDataset, MultiTimeframeFetcher, Timeframe

TIMEFRAME_ORDER: tuple[str, ...] = ("5m", "1h", "1d")
TIMEFRAME_LABELS: dict[str, str] = {
    "5m": "5분봉",
    "1h": "1시간봉",
    "1d": "일봉",
}
US_EXCHANGES: tuple[str, ...] = ("NASD", "NYSE", "AMEX")


class SmartMoneyFetcher(Protocol):
    def fetch_symbol(
        self,
        symbol: str,
        market: str = "KR",
        exchange: str = "NASD",
    ) -> MultiTimeframeDataset:
        """종목의 멀티타임프레임 OHLCV 데이터를 수집한다."""


FigureBuilder = Callable[[pd.DataFrame, TimeframePatternReport, SmartMoneySignal | None], Any]
AlertDispatcher = Callable[..., SmartMoneyAlertResult]
SystemAlertDispatcher = Callable[..., SmartMoneyAlertResult]


@dataclass
class SmartMoneySymbolAnalysis:
    symbol: str
    market: str
    exchange: str
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    reports: dict[str, TimeframePatternReport] = field(default_factory=dict)
    signal: SmartMoneySignal | None = None
    timeframe_errors: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """표시 가능한 최종 신호가 있으면 성공 결과로 본다."""
        return self.signal is not None and self.error is None


def parse_symbol_input(value: str) -> list[str]:
    """쉼표/줄바꿈으로 입력한 종목 문자열을 중복 없는 종목 리스트로 변환한다."""
    if not isinstance(value, str):
        raise ValueError("종목 입력은 문자열이어야 합니다.")

    symbols: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[,\r\n]+", value):
        symbol = token.strip().upper()
        if not symbol or symbol in seen:
            continue
        symbols.append(symbol)
        seen.add(symbol)
    return symbols


def run_smart_money_batch(
    symbol_text: str,
    *,
    market: str,
    exchange: str,
    fetcher: SmartMoneyFetcher | None = None,
    config: SignalConfig | None = None,
    alert_config: SmartMoneyAlertConfig | None = None,
    alert_dispatcher: AlertDispatcher = dispatch_smart_money_alert,
    system_alert_dispatcher: SystemAlertDispatcher = dispatch_smart_money_system_alert,
) -> list[SmartMoneySymbolAnalysis]:
    """여러 종목 Smart Money 분석을 순차 실행하고 종목별 실패를 격리한다."""
    symbols = parse_symbol_input(symbol_text)
    if not symbols:
        return []

    active_fetcher = fetcher or MultiTimeframeFetcher()
    active_config = config or SignalConfig()
    results: list[SmartMoneySymbolAnalysis] = []
    for symbol in symbols:
        results.append(
            analyze_smart_money_symbol(
                symbol,
                market=market,
                exchange=exchange,
                fetcher=active_fetcher,
                config=active_config,
                alert_config=alert_config,
                alert_dispatcher=alert_dispatcher,
                system_alert_dispatcher=system_alert_dispatcher,
            )
        )
    return results


def analyze_smart_money_symbol(
    symbol: str,
    *,
    market: str,
    exchange: str,
    fetcher: SmartMoneyFetcher,
    config: SignalConfig,
    alert_config: SmartMoneyAlertConfig | None = None,
    alert_dispatcher: AlertDispatcher = dispatch_smart_money_alert,
    system_alert_dispatcher: SystemAlertDispatcher = dispatch_smart_money_system_alert,
) -> SmartMoneySymbolAnalysis:
    """단일 종목을 수집, 패턴 분석, 최종 신호 산출 순서로 처리한다."""
    try:
        dataset = fetcher.fetch_symbol(symbol, market=market, exchange=exchange)
    except Exception as exc:
        timeframe_errors: dict[str, str] = {}
        system_alert = _dispatch_system_alert_for_dashboard(
            symbol=symbol,
            stage="data_fetch",
            error=str(exc),
            alert_config=alert_config,
            system_alert_dispatcher=system_alert_dispatcher,
        )
        if system_alert is not None and system_alert.should_notify and not system_alert.sent:
            timeframe_errors["system_alert"] = (
                f"Smart Money system alert failed: {system_alert.reason}"
            )
        return SmartMoneySymbolAnalysis(
            symbol=symbol,
            market=market,
            exchange=exchange,
            timeframe_errors=timeframe_errors,
            error=f"데이터 수집 실패: {exc}",
        )

    timeframe_errors = _collect_timeframe_errors(dataset)
    frames = dataset.successful_ohlcv()
    if not frames:
        system_alert = _dispatch_system_alert_for_dashboard(
            symbol=dataset.symbol,
            stage="no_timeframe_data",
            error="분석 가능한 timeframe 데이터가 없습니다.",
            alert_config=alert_config,
            system_alert_dispatcher=system_alert_dispatcher,
        )
        if system_alert is not None and system_alert.should_notify and not system_alert.sent:
            timeframe_errors["system_alert"] = (
                f"Smart Money system alert failed: {system_alert.reason}"
            )
        return SmartMoneySymbolAnalysis(
            symbol=dataset.symbol,
            market=dataset.market,
            exchange=dataset.exchange,
            timeframe_errors=timeframe_errors,
            error="분석 가능한 timeframe 데이터가 없습니다.",
        )

    try:
        reports = analyze_multi_timeframe_patterns(frames)
        signal = combine_multi_timeframe_signals(reports, config)
    except Exception as exc:
        system_alert = _dispatch_system_alert_for_dashboard(
            symbol=dataset.symbol,
            stage="pattern_analysis",
            error=str(exc),
            alert_config=alert_config,
            system_alert_dispatcher=system_alert_dispatcher,
        )
        if system_alert is not None and system_alert.should_notify and not system_alert.sent:
            timeframe_errors["system_alert"] = (
                f"Smart Money system alert failed: {system_alert.reason}"
            )
        return SmartMoneySymbolAnalysis(
            symbol=dataset.symbol,
            market=dataset.market,
            exchange=dataset.exchange,
            frames=frames,
            timeframe_errors=timeframe_errors,
            error=f"패턴 분석 실패: {exc}",
        )

    timeframe_errors = dict(timeframe_errors)
    if alert_config is not None and alert_config.enabled:
        alert_result = _dispatch_alert_for_dashboard(
            symbol=dataset.symbol,
            signal=signal,
            reports=reports,
            alert_config=alert_config,
            alert_dispatcher=alert_dispatcher,
        )
        if alert_result.should_notify and not alert_result.sent:
            timeframe_errors["alert"] = f"Smart Money alert failed: {alert_result.reason}"

    return SmartMoneySymbolAnalysis(
        symbol=dataset.symbol,
        market=dataset.market,
        exchange=dataset.exchange,
        frames=frames,
        reports=reports,
        signal=signal,
        timeframe_errors=timeframe_errors,
    )


def build_result_rows(results: Sequence[SmartMoneySymbolAnalysis]) -> list[dict[str, object]]:
    """결과 표에 표시할 고정 컬럼 row를 만든다."""
    rows: list[dict[str, object]] = []
    for result in results:
        signal = result.signal
        rows.append(
            {
                "symbol": result.symbol,
                "signal": signal.signal if signal else "ERROR",
                "confidence": _format_confidence(signal.confidence if signal else 0.0),
                "daily structure": _format_daily_structure(result),
                "1h setup": _format_hourly_setup(result),
                "5m trigger": _format_minute_trigger(result),
                "entry zone": _format_entry_zone(signal),
                "invalidation": _format_invalidation(signal),
                "주요 reason": _format_primary_reason(result),
            }
        )
    return rows


def collect_warnings(result: SmartMoneySymbolAnalysis) -> list[str]:
    """timeframe 수집 실패와 신호 warning을 사용자 표시용 목록으로 모은다."""
    warnings: list[str] = [
        f"{timeframe}: {error}" for timeframe, error in result.timeframe_errors.items()
    ]
    if result.signal is not None:
        warnings.extend(result.signal.warnings)
    return _deduplicate(warnings)


def build_selected_chart(
    result: SmartMoneySymbolAnalysis,
    timeframe: str,
    *,
    figure_builder: FigureBuilder = build_smart_money_figure,
) -> Any | None:
    """선택 timeframe의 frame/report/signal 조합으로 annotated chart를 만든다."""
    frame = result.frames.get(timeframe)
    report = result.reports.get(timeframe)
    if frame is None or report is None:
        return None
    return figure_builder(frame, report, result.signal)


def load_smart_money_alert_config() -> SmartMoneyAlertConfig:
    """config/trading.yaml의 smart_money.alerts 설정을 로드한다."""
    from importlib import import_module

    config_loader = import_module("src.utils.config_loader")
    trading_config = config_loader.get_trading_config()
    smart_money_config = trading_config.get("smart_money", {})
    if not isinstance(smart_money_config, dict):
        return SmartMoneyAlertConfig()
    alerts_config = smart_money_config.get("alerts", {})
    if not isinstance(alerts_config, dict):
        return SmartMoneyAlertConfig()
    return build_smart_money_alert_config(alerts_config)


def _dispatch_alert_for_dashboard(
    *,
    symbol: str,
    signal: SmartMoneySignal,
    reports: dict[str, TimeframePatternReport],
    alert_config: SmartMoneyAlertConfig,
    alert_dispatcher: AlertDispatcher,
) -> SmartMoneyAlertResult:
    """대시보드 분석 흐름에서 알림 실패를 결과 경고로 격리한다."""
    try:
        return alert_dispatcher(
            symbol=symbol,
            signal=signal,
            current_price=_latest_close_from_reports(reports),
            timeframe_summary=_timeframe_summary(reports),
            config=alert_config,
        )
    except Exception as exc:
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="dispatch_exception",
            provider=alert_config.provider,
            error=str(exc),
        )


def _dispatch_system_alert_for_dashboard(
    *,
    symbol: str,
    stage: str,
    error: str,
    alert_config: SmartMoneyAlertConfig | None,
    system_alert_dispatcher: SystemAlertDispatcher,
) -> SmartMoneyAlertResult | None:
    """대시보드 실패 흐름에서 system alert 실패를 결과 경고로 격리한다."""
    if alert_config is None or not alert_config.enabled:
        return None
    try:
        return system_alert_dispatcher(
            message=f"{symbol.strip().upper()} {stage}: {error}",
            config=alert_config,
        )
    except Exception as exc:
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="dispatch_exception",
            provider=alert_config.provider,
            error=str(exc),
        )


def render_smart_money_tab(st_api: Any = st) -> None:
    """Streamlit Smart Money 탭을 렌더링한다."""
    st_api.header("Smart Money 멀티타임프레임 분석")

    col1, col2, col3 = st_api.columns([3, 1, 1])
    with col1:
        symbol_text = st_api.text_area(
            "종목 입력",
            value="AAPL, MSFT",
            height=96,
            help="쉼표 또는 줄바꿈으로 여러 종목을 입력하세요.",
            key="smart_money_symbols",
        )
    with col2:
        market = st_api.selectbox("시장", ["KR", "US"], index=1, key="smart_money_market")
    with col3:
        if market == "US":
            exchange = st_api.selectbox(
                "거래소",
                list(US_EXCHANGES),
                index=0,
                key="smart_money_exchange",
            )
        else:
            exchange = "KRX"
            st_api.caption("KR 시장은 KRX 기준으로 분석합니다.")

    if st_api.button("분석 실행", type="primary", key="smart_money_run"):
        symbols = parse_symbol_input(symbol_text)
        if not symbols:
            st_api.warning("분석할 종목을 하나 이상 입력하세요.")
            st_api.session_state["smart_money_results"] = []
        else:
            with st_api.spinner("Smart Money 분석을 실행하는 중입니다."):
                alert_config = load_smart_money_alert_config()
                st_api.session_state["smart_money_results"] = run_smart_money_batch(
                    symbol_text,
                    market=market,
                    exchange=exchange,
                    alert_config=alert_config,
                )

    results = st_api.session_state.get("smart_money_results", [])
    if not results:
        st_api.info("종목을 입력하고 분석 실행 버튼을 누르면 결과가 표시됩니다.")
        return

    _render_results(results, st_api=st_api)


def _render_results(results: Sequence[SmartMoneySymbolAnalysis], *, st_api: Any) -> None:
    success_results = [result for result in results if result.is_success]
    if not success_results:
        st_api.error("모든 종목의 Smart Money 분석에 실패했습니다.")
    elif len(success_results) < len(results):
        st_api.warning("일부 종목 또는 timeframe 분석에 실패했습니다. 성공 결과는 계속 표시합니다.")

    st_api.dataframe(pd.DataFrame(build_result_rows(results)), use_container_width=True)

    for result in results:
        warnings = collect_warnings(result)
        if result.error:
            st_api.warning(f"{result.symbol}: {result.error}")
        for warning in warnings:
            st_api.warning(f"{result.symbol}: {warning}")

    if not success_results:
        return

    selected_symbol = st_api.selectbox(
        "상세 종목",
        [result.symbol for result in success_results],
        key="smart_money_detail_symbol",
    )
    selected = next(result for result in success_results if result.symbol == selected_symbol)
    _render_detail(selected, st_api=st_api)


def _render_detail(result: SmartMoneySymbolAnalysis, *, st_api: Any) -> None:
    st_api.subheader(f"{result.symbol} 상세 분석")
    tabs = st_api.tabs([TIMEFRAME_LABELS[key] for key in TIMEFRAME_ORDER])
    for tab, timeframe in zip(tabs, TIMEFRAME_ORDER, strict=True):
        with tab:
            report = result.reports.get(timeframe)
            frame = result.frames.get(timeframe)
            if report is None or frame is None:
                st_api.warning(
                    f"{TIMEFRAME_LABELS[timeframe]} 데이터가 없어 차트를 표시할 수 없습니다."
                )
                continue

            try:
                figure = build_selected_chart(result, timeframe)
            except Exception as exc:
                st_api.warning(f"{TIMEFRAME_LABELS[timeframe]} 차트 생성 실패: {exc}")
                figure = None

            if isinstance(figure, go.Figure):
                st_api.plotly_chart(figure, use_container_width=True)
            _render_pattern_summary(report, st_api=st_api)


def _render_pattern_summary(report: TimeframePatternReport, *, st_api: Any) -> None:
    summary = report.summary
    st_api.markdown(
        "\n".join(
            [
                f"- 시장 구조: {report.market_structure.value}",
                f"- 스윙: {summary.swing_count}개",
                f"- 구조 돌파: {summary.structure_break_count}개",
                f"- 활성 FVG: {summary.open_fvg_count + summary.touched_fvg_count}개",
                "- 활성 오더블록: "
                f"{summary.fresh_order_block_count + summary.mitigated_order_block_count}개",
                f"- Liquidity sweep: {summary.liquidity_sweep_count}개",
                "- 최근 캔들 패턴: "
                f"{summary.bullish_pattern_count + summary.bearish_pattern_count + summary.neutral_pattern_count}개",
            ]
        )
    )
    for warning in report.warnings:
        st_api.warning(warning)


def _latest_close_from_reports(reports: dict[str, TimeframePatternReport]) -> float | None:
    for timeframe in ("5m", "1h", "1d"):
        report = reports.get(timeframe)
        if report is not None and report.latest_close is not None:
            return float(report.latest_close)
    return None


def _timeframe_summary(reports: dict[str, TimeframePatternReport]) -> list[str]:
    summary: list[str] = []
    for timeframe in TIMEFRAME_ORDER:
        report = reports.get(timeframe)
        if report is None:
            continue
        summary.append(f"{timeframe} {report.market_structure.value}")
    return summary


def _collect_timeframe_errors(dataset: MultiTimeframeDataset) -> dict[str, str]:
    errors: dict[str, str] = {}
    for timeframe in Timeframe:
        result = dataset.get(timeframe)
        if result.error:
            errors[timeframe.value] = result.error
    return errors


def _format_confidence(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_daily_structure(result: SmartMoneySymbolAnalysis) -> str:
    report = result.reports.get("1d")
    if report is None:
        return "-"
    return report.market_structure.value


def _format_hourly_setup(result: SmartMoneySymbolAnalysis) -> str:
    report = result.reports.get("1h")
    if report is None:
        return "-"
    summary = report.summary
    fvg_count = summary.open_fvg_count + summary.touched_fvg_count
    order_block_count = summary.fresh_order_block_count + summary.mitigated_order_block_count
    return f"FVG {fvg_count} / OB {order_block_count}"


def _format_minute_trigger(result: SmartMoneySymbolAnalysis) -> str:
    report = result.reports.get("5m")
    if report is None:
        return "-"
    summary = report.summary
    pattern_count = (
        summary.bullish_pattern_count
        + summary.bearish_pattern_count
        + summary.neutral_pattern_count
    )
    return (
        f"구조돌파 {summary.structure_break_count} / "
        f"스윕 {summary.liquidity_sweep_count} / "
        f"캔들패턴 {pattern_count}"
    )


def _format_entry_zone(signal: SmartMoneySignal | None) -> str:
    if signal is None or signal.entry_zone is None:
        return "-"
    lower, upper = signal.entry_zone
    return f"{lower:.2f} ~ {upper:.2f}"


def _format_invalidation(signal: SmartMoneySignal | None) -> str:
    if signal is None or signal.invalidation_level is None:
        return "-"
    return f"{signal.invalidation_level:.2f}"


def _format_primary_reason(result: SmartMoneySymbolAnalysis) -> str:
    if result.signal is not None and result.signal.reasons:
        return result.signal.reasons[0]
    warnings = collect_warnings(result)
    if warnings:
        return warnings[0]
    return result.error or "-"


def _deduplicate(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
