"""Smart Money CLI/스케줄러용 분석 리포트 생성기."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd

# `python scripts/run_smart_money_analysis.py` 직접 실행 시 src 패키지를 찾도록 보정한다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.smart_money import (
    SignalConfig,
    SmartMoneyAlertConfig,
    SmartMoneyAlertResult,
    SmartMoneyPatternConfig,
    SmartMoneySignal,
    TimeframePatternReport,
    analyze_multi_timeframe_patterns,
    build_smart_money_alert_config,
    combine_multi_timeframe_signals,
    dispatch_smart_money_alert,
    dispatch_smart_money_system_alert,
    load_smart_money_analysis_config,
)
from src.analysis.timeframes import (
    MultiTimeframeDataset,
    MultiTimeframeFetcher,
    Timeframe,
    TimeframeData,
)

ReportPayload = dict[str, Any]
Clock = Callable[[], datetime]

TIMEFRAME_ORDER: tuple[str, ...] = ("1d", "1h", "5m")
DEFAULT_MARKET: str = "US"
DEFAULT_EXCHANGE: str = "NASD"


class SmartMoneyFetcher(Protocol):
    """CLI가 필요로 하는 멀티타임프레임 fetcher 계약."""

    def fetch_symbol(
        self,
        symbol: str,
        market: str = "KR",
        exchange: str = "NASD",
    ) -> MultiTimeframeDataset:
        """종목별 멀티타임프레임 OHLCV 묶음을 반환한다."""


class SmartMoneyAlertDispatcher(Protocol):
    """Smart Money 분석 결과 알림 전송 계약."""

    def __call__(
        self,
        *,
        symbol: str,
        signal: SmartMoneySignal,
        current_price: float | None = None,
        timeframe_summary: Sequence[str] | None = None,
        config: SmartMoneyAlertConfig | None = None,
        now: datetime | None = None,
    ) -> SmartMoneyAlertResult:
        """분석된 신호를 알림 provider로 전달한다."""


class SmartMoneySystemAlertDispatcher(Protocol):
    """Smart Money 시스템 알림 전송 계약."""

    def __call__(
        self,
        *,
        message: str,
        config: SmartMoneyAlertConfig | None = None,
        now: datetime | None = None,
    ) -> SmartMoneyAlertResult:
        """실패 경로를 매매 신호 알림과 분리된 system alert로 전달한다."""


def parse_symbols(value: str) -> list[str]:
    """쉼표/줄바꿈으로 입력된 symbol 목록을 대문자 중복 제거 리스트로 변환한다."""
    if not isinstance(value, str):
        raise ValueError("symbols 입력은 문자열이어야 합니다.")

    symbols: list[str] = []
    seen: set[str] = set()
    for token in value.replace("\n", ",").split(","):
        symbol = token.strip().upper()
        if not symbol or symbol in seen:
            continue
        symbols.append(symbol)
        seen.add(symbol)
    return symbols


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="Smart Money 멀티타임프레임 분석 JSON/Markdown 리포트 생성"
    )
    parser.add_argument("--symbols", required=True, help="분석할 종목 목록. 예: AAPL,MSFT")
    parser.add_argument("--market", default=DEFAULT_MARKET, choices=("KR", "US"), help="시장 구분")
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE, help="거래소 코드")
    parser.add_argument("--output", default=None, help="리포트 출력 경로")
    parser.add_argument("--format", default="json", choices=("json", "markdown"), help="출력 형식")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="네트워크 없이 합성 fixture 데이터로 분석한다.",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="외부 네트워크 호출을 금지하고 fixture 데이터로 분석한다.",
    )
    return parser


def load_smart_money_alert_config() -> SmartMoneyAlertConfig:
    """config/trading.yaml의 smart_money.alerts 설정을 로드한다."""
    from importlib import import_module

    config_loader = import_module("src.utils.config_loader")
    trading_config = config_loader.get_trading_config()
    smart_money_config = trading_config.get("smart_money", {})
    if not isinstance(smart_money_config, Mapping):
        return SmartMoneyAlertConfig()
    alerts_config = smart_money_config.get("alerts", {})
    if not isinstance(alerts_config, Mapping):
        return SmartMoneyAlertConfig()
    return build_smart_money_alert_config(alerts_config)


def build_report_payload(
    symbols: Sequence[str],
    *,
    market: str,
    exchange: str,
    generated_at: datetime,
    fetcher: SmartMoneyFetcher,
    config: SignalConfig | None = None,
    pattern_config: SmartMoneyPatternConfig | None = None,
    alert_config: SmartMoneyAlertConfig | None = None,
    alert_dispatcher: SmartMoneyAlertDispatcher = dispatch_smart_money_alert,
    system_alert_dispatcher: SmartMoneySystemAlertDispatcher = dispatch_smart_money_system_alert,
) -> ReportPayload:
    """종목별 Smart Money 분석 결과를 JSON 직렬화 가능한 payload로 만든다."""
    active_config = config or SignalConfig()
    results = [
        analyze_symbol(
            symbol,
            market=market,
            exchange=exchange,
            fetcher=fetcher,
            config=active_config,
            pattern_config=pattern_config,
            alert_config=alert_config,
            alert_dispatcher=alert_dispatcher,
            system_alert_dispatcher=system_alert_dispatcher,
            generated_at=generated_at,
        )
        for symbol in symbols
    ]
    success_count = sum(1 for item in results if item["status"] == "success")
    return {
        "generated_at": _isoformat(generated_at),
        "market": market,
        "exchange": exchange,
        "summary": {
            "total_symbols": len(results),
            "success_count": success_count,
            "failure_count": len(results) - success_count,
        },
        "results": results,
    }


def analyze_symbol(
    symbol: str,
    *,
    market: str,
    exchange: str,
    fetcher: SmartMoneyFetcher,
    config: SignalConfig,
    pattern_config: SmartMoneyPatternConfig | None = None,
    alert_config: SmartMoneyAlertConfig | None = None,
    alert_dispatcher: SmartMoneyAlertDispatcher = dispatch_smart_money_alert,
    system_alert_dispatcher: SmartMoneySystemAlertDispatcher = dispatch_smart_money_system_alert,
    generated_at: datetime | None = None,
) -> ReportPayload:
    """단일 종목 수집, 패턴 분석, 최종 신호 산출을 격리 실행한다."""
    try:
        dataset = fetcher.fetch_symbol(symbol, market=market, exchange=exchange)
    except Exception as exc:
        system_alert = _dispatch_system_alert_if_enabled(
            symbol=symbol,
            stage="data_fetch",
            error=_format_exception(exc),
            alert_config=alert_config,
            system_alert_dispatcher=system_alert_dispatcher,
            generated_at=generated_at,
        )
        return _error_result(
            symbol=symbol,
            market=market,
            exchange=exchange,
            error=f"데이터 수집 실패: {_format_exception(exc)}",
            system_alert=system_alert,
        )

    timeframe_errors = _collect_timeframe_errors(dataset)
    frames = dataset.successful_ohlcv()
    if not frames:
        system_alert = _dispatch_system_alert_if_enabled(
            symbol=dataset.symbol,
            stage="no_timeframe_data",
            error="분석 가능한 timeframe 데이터가 없습니다.",
            alert_config=alert_config,
            system_alert_dispatcher=system_alert_dispatcher,
            generated_at=generated_at,
        )
        return _error_result(
            symbol=dataset.symbol,
            market=dataset.market,
            exchange=dataset.exchange,
            error="분석 가능한 timeframe 데이터가 없습니다.",
            timeframe_errors=timeframe_errors,
            system_alert=system_alert,
        )

    try:
        reports = (
            analyze_multi_timeframe_patterns(frames, pattern_config=pattern_config)
            if pattern_config is not None
            else analyze_multi_timeframe_patterns(frames)
        )
        signal = combine_multi_timeframe_signals(reports, config)
    except Exception as exc:
        system_alert = _dispatch_system_alert_if_enabled(
            symbol=dataset.symbol,
            stage="pattern_analysis",
            error=_format_exception(exc),
            alert_config=alert_config,
            system_alert_dispatcher=system_alert_dispatcher,
            generated_at=generated_at,
        )
        return _error_result(
            symbol=dataset.symbol,
            market=dataset.market,
            exchange=dataset.exchange,
            error=f"패턴 분석 실패: {_format_exception(exc)}",
            timeframe_errors=timeframe_errors,
            system_alert=system_alert,
        )

    warnings = _collect_warnings(timeframe_errors, reports, signal)
    alert_result = _dispatch_alert_if_enabled(
        symbol=dataset.symbol,
        signal=signal,
        reports=reports,
        alert_config=alert_config,
        alert_dispatcher=alert_dispatcher,
        generated_at=generated_at,
    )
    if alert_result is not None and alert_result.should_notify and not alert_result.sent:
        warnings.append(f"Smart Money alert failed: {alert_result.reason}")
    return {
        "symbol": dataset.symbol,
        "market": dataset.market,
        "exchange": dataset.exchange,
        "status": "success",
        "signal": signal.signal,
        "confidence": signal.confidence,
        "score": signal.score,
        "risk_level": signal.risk_level,
        "entry_zone": _serialize_entry_zone(signal.entry_zone),
        "invalidation": signal.invalidation_level,
        "take_profit_candidates": signal.take_profit_candidates,
        "reasons": list(signal.reasons),
        "warnings": warnings,
        "alert": _serialize_alert_result(alert_result),
        "error": None,
        "timeframes": _serialize_timeframes(reports, timeframe_errors),
    }


def _dispatch_alert_if_enabled(
    *,
    symbol: str,
    signal: SmartMoneySignal,
    reports: Mapping[str, TimeframePatternReport],
    alert_config: SmartMoneyAlertConfig | None,
    alert_dispatcher: SmartMoneyAlertDispatcher,
    generated_at: datetime | None,
) -> SmartMoneyAlertResult | None:
    """설정이 켜진 경우에만 Smart Money 알림을 전송한다."""
    if alert_config is None or not alert_config.enabled:
        return None
    try:
        return alert_dispatcher(
            symbol=symbol,
            signal=signal,
            current_price=_latest_close_from_reports(reports),
            timeframe_summary=_timeframe_summary(reports),
            config=alert_config,
            now=generated_at,
        )
    except Exception as exc:
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="dispatch_exception",
            provider=alert_config.provider,
            error=_format_exception(exc),
        )


def _dispatch_system_alert_if_enabled(
    *,
    symbol: str,
    stage: str,
    error: str,
    alert_config: SmartMoneyAlertConfig | None,
    system_alert_dispatcher: SmartMoneySystemAlertDispatcher,
    generated_at: datetime | None,
) -> SmartMoneyAlertResult | None:
    """설정이 켜진 경우 실패 경로를 system alert로 전송한다."""
    if alert_config is None or not alert_config.enabled:
        return None
    message = f"{symbol.strip().upper()} {stage}: {error}"
    try:
        return system_alert_dispatcher(
            message=message,
            config=alert_config,
            now=generated_at,
        )
    except Exception as exc:
        return SmartMoneyAlertResult(
            should_notify=True,
            sent=False,
            reason="dispatch_exception",
            provider=alert_config.provider,
            error=_format_exception(exc),
        )


def _serialize_alert_result(result: SmartMoneyAlertResult | None) -> dict[str, Any] | None:
    """알림 전송 결과를 리포트 payload에 넣을 수 있게 직렬화한다."""
    if result is None:
        return None
    return {
        "should_notify": result.should_notify,
        "sent": result.sent,
        "reason": result.reason,
        "provider": result.provider,
        "error": result.error,
        "state_saved": result.state_saved,
    }


def _latest_close_from_reports(reports: Mapping[str, TimeframePatternReport]) -> float | None:
    """메시지 현재가로 사용할 가장 짧은 timeframe의 최신 종가를 고른다."""
    for timeframe in ("5m", "1h", "1d"):
        report = reports.get(timeframe)
        if report is not None and report.latest_close is not None:
            return float(report.latest_close)
    return None


def _timeframe_summary(reports: Mapping[str, TimeframePatternReport]) -> list[str]:
    """알림 메시지에 넣을 timeframe 구조 요약을 만든다."""
    summary: list[str] = []
    for timeframe in TIMEFRAME_ORDER:
        report = reports.get(timeframe)
        if report is None:
            continue
        summary.append(f"{timeframe} {report.market_structure.value}")
    return summary


def render_markdown(payload: Mapping[str, Any]) -> str:
    """리포트 payload를 스케줄러가 읽기 쉬운 Markdown으로 렌더링한다."""
    lines = [
        "# Smart Money 분석 리포트",
        "",
        f"- 실행 시각: {payload['generated_at']}",
        f"- 시장: {payload['market']}",
        f"- 거래소: {payload['exchange']}",
        "",
        "## 요약",
        "",
        "| symbol | signal | confidence | entry | invalidation | warnings |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for result in cast(Sequence[Mapping[str, Any]], payload["results"]):
        lines.append(
            "| {symbol} | {signal} | {confidence} | {entry} | {invalidation} | {warnings} |".format(
                symbol=result["symbol"],
                signal=result["signal"],
                confidence=_format_percent(cast(float, result["confidence"])),
                entry=_format_entry(result.get("entry_zone")),
                invalidation=_format_optional_float(result.get("invalidation")),
                warnings=len(cast(Sequence[str], result["warnings"])),
            )
        )

    for result in cast(Sequence[Mapping[str, Any]], payload["results"]):
        lines.extend(_render_symbol_markdown(result))
    return "\n".join(lines) + "\n"


def write_report(payload: Mapping[str, Any], *, output: Path, output_format: str) -> None:
    """리포트를 지정 경로에 쓴다."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    if output_format == "markdown":
        output.write_text(render_markdown(payload), encoding="utf-8")
        return
    raise ValueError(f"지원하지 않는 리포트 형식입니다: {output_format}")


def main(argv: Sequence[str] | None = None, *, clock: Clock | None = None) -> int:
    """CLI 진입점."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        symbols = parse_symbols(args.symbols)
    except ValueError as exc:
        print(f"[smart-money] 입력 오류: {exc}", file=sys.stderr)
        return 2
    if not symbols:
        print("[smart-money] 분석할 종목을 1개 이상 입력해주세요.", file=sys.stderr)
        return 2

    now = (clock or datetime.now)()
    output = Path(args.output) if args.output else _default_output_path(args.format, now)
    fetcher: SmartMoneyFetcher = (
        FixtureSmartMoneyFetcher() if args.fixture or args.no_network else MultiTimeframeFetcher()
    )

    try:
        alert_config = load_smart_money_alert_config()
        signal_config, pattern_config = load_smart_money_analysis_config()
        payload = build_report_payload(
            symbols,
            market=args.market,
            exchange=args.exchange,
            generated_at=now,
            fetcher=fetcher,
            config=signal_config,
            pattern_config=pattern_config,
            alert_config=alert_config,
        )
        write_report(payload, output=output, output_format=args.format)
    except Exception as exc:
        print(f"[smart-money] 리포트 생성 실패: {_format_exception(exc)}", file=sys.stderr)
        return 1

    if payload["summary"]["success_count"] == 0:
        return 1
    return 0


class FixtureSmartMoneyFetcher:
    """네트워크 호출 없이 CLI 계약을 검증하기 위한 합성 fetcher."""

    def fetch_symbol(
        self,
        symbol: str,
        market: str = "KR",
        exchange: str = "NASD",
    ) -> MultiTimeframeDataset:
        """fixture symbol 규칙에 따라 성공/부분 실패/전체 실패 데이터를 반환한다."""
        clean_symbol = symbol.strip().upper()
        if clean_symbol.startswith("FAIL"):
            raise RuntimeError("fixture requested failure")

        timeframes = {
            Timeframe.MINUTE_5: TimeframeData(
                timeframe=Timeframe.MINUTE_5,
                data=_make_fixture_ohlcv("5min", 48, 100.0, 0.20),
                source="fixture:5m",
            ),
            Timeframe.HOUR_1: TimeframeData(
                timeframe=Timeframe.HOUR_1,
                data=_make_fixture_ohlcv("1h", 48, 101.0, 0.35),
                source="fixture:1h",
            ),
            Timeframe.DAY_1: TimeframeData(
                timeframe=Timeframe.DAY_1,
                data=_make_fixture_ohlcv("1D", 48, 102.0, 0.50),
                source="fixture:1d",
            ),
        }
        if clean_symbol == "PARTIAL":
            timeframes[Timeframe.DAY_1] = TimeframeData(
                timeframe=Timeframe.DAY_1,
                error="fixture daily failure",
                source="fixture:1d",
            )

        return MultiTimeframeDataset(
            symbol=clean_symbol,
            market=market.strip().upper(),
            exchange=exchange.strip().upper(),
            timeframes=timeframes,
        )


def _error_result(
    *,
    symbol: str,
    market: str,
    exchange: str,
    error: str,
    timeframe_errors: Mapping[str, str] | None = None,
    system_alert: SmartMoneyAlertResult | None = None,
) -> ReportPayload:
    """종목 실패 결과를 표준 리포트 row로 만든다."""
    errors = dict(timeframe_errors or {})
    warnings = _deduplicate(list(errors.values()) + [error])
    if system_alert is not None and system_alert.should_notify and not system_alert.sent:
        warnings.append(f"Smart Money system alert failed: {system_alert.reason}")
    return {
        "symbol": symbol,
        "market": market,
        "exchange": exchange,
        "status": "error",
        "signal": "ERROR",
        "confidence": 0.0,
        "score": 0.0,
        "risk_level": "HIGH",
        "entry_zone": None,
        "invalidation": None,
        "take_profit_candidates": [],
        "reasons": [],
        "warnings": warnings,
        "alert": None,
        "system_alert": _serialize_alert_result(system_alert),
        "error": error,
        "timeframes": _serialize_timeframes({}, errors),
    }


def _serialize_timeframes(
    reports: Mapping[str, TimeframePatternReport],
    timeframe_errors: Mapping[str, str],
) -> dict[str, Any]:
    """timeframe별 summary와 실패 정보를 직렬화한다."""
    payload: dict[str, Any] = {}
    for timeframe in TIMEFRAME_ORDER:
        if timeframe in timeframe_errors:
            payload[timeframe] = {"status": "error", "error": timeframe_errors[timeframe]}
            continue
        report = reports.get(timeframe)
        if report is None:
            payload[timeframe] = {"status": "missing", "error": "리포트가 없습니다."}
            continue
        payload[timeframe] = _serialize_report_summary(report)
    return payload


def _serialize_report_summary(report: TimeframePatternReport) -> dict[str, Any]:
    """TimeframePatternReport의 핵심 summary 필드만 추출한다."""
    summary = report.summary
    return {
        "status": "success",
        "market_structure": report.market_structure.value,
        "latest_close": report.latest_close,
        "latest_bar_index": report.latest_bar_index,
        "summary": {
            "swings": summary.swing_count,
            "structure_breaks": summary.structure_break_count,
            "open_fvgs": summary.open_fvg_count,
            "touched_fvgs": summary.touched_fvg_count,
            "filled_fvgs": summary.filled_fvg_count,
            "fresh_order_blocks": summary.fresh_order_block_count,
            "mitigated_order_blocks": summary.mitigated_order_block_count,
            "invalidated_order_blocks": summary.invalidated_order_block_count,
            "liquidity_sweeps": summary.liquidity_sweep_count,
            "bullish_patterns": summary.bullish_pattern_count,
            "bearish_patterns": summary.bearish_pattern_count,
            "neutral_patterns": summary.neutral_pattern_count,
        },
        "warnings": list(report.warnings),
    }


def _collect_timeframe_errors(dataset: MultiTimeframeDataset) -> dict[str, str]:
    """MultiTimeframeDataset에서 timeframe별 실패만 추출한다."""
    errors: dict[str, str] = {}
    for timeframe in Timeframe:
        result = dataset.get(timeframe)
        if result.error:
            errors[timeframe.value] = result.error
    return errors


def _collect_warnings(
    timeframe_errors: Mapping[str, str],
    reports: Mapping[str, TimeframePatternReport],
    signal: SmartMoneySignal,
) -> list[str]:
    """수집 실패, 리포트 경고, 신호 경고를 사용자용 warning 목록으로 합친다."""
    warnings: list[str] = [f"{timeframe}: {error}" for timeframe, error in timeframe_errors.items()]
    for report in reports.values():
        warnings.extend(report.warnings)
    warnings.extend(signal.warnings)
    return _deduplicate(warnings)


def _serialize_entry_zone(entry_zone: tuple[float, float] | None) -> dict[str, float] | None:
    """entry zone 튜플을 JSON 객체로 변환한다."""
    if entry_zone is None:
        return None
    return {"lower": float(entry_zone[0]), "upper": float(entry_zone[1])}


def _make_fixture_ohlcv(freq: str, rows: int, base_price: float, step: float) -> pd.DataFrame:
    """분석 엔진이 처리할 수 있는 합성 OHLCV DataFrame을 만든다."""
    index = pd.date_range("2024-01-02", periods=rows, freq=freq)
    closes = [base_price + step * idx for idx in range(rows)]
    data = []
    for idx, close in enumerate(closes):
        open_price = close - (step * 0.5)
        high = max(open_price, close) + 1.0 + (0.1 if idx % 5 == 0 else 0.0)
        low = min(open_price, close) - 1.0 - (0.1 if idx % 7 == 0 else 0.0)
        data.append(
            {
                "open": float(open_price),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(10_000 + idx * 10),
            }
        )
    return pd.DataFrame(data, index=index)


def _render_symbol_markdown(result: Mapping[str, Any]) -> list[str]:
    """단일 종목 상세 섹션을 Markdown 줄 목록으로 만든다."""
    lines = [
        "",
        f"## {result['symbol']}",
        "",
        f"- signal: {result['signal']}",
        f"- confidence: {_format_percent(cast(float, result['confidence']))}",
        f"- entry: {_format_entry(result.get('entry_zone'))}",
        f"- invalidation: {_format_optional_float(result.get('invalidation'))}",
        "",
        "### reasons",
    ]
    reasons = cast(Sequence[str], result["reasons"])
    lines.extend([f"- {reason}" for reason in reasons] or ["- -"])
    lines.extend(["", "### warnings"])
    warnings = cast(Sequence[str], result["warnings"])
    lines.extend([f"- {warning}" for warning in warnings] or ["- -"])
    lines.extend(
        ["", "### timeframes", "", "| timeframe | status | structure | close | warnings |"]
    )
    lines.append("|---|---|---|---:|---:|")
    for timeframe, summary in cast(Mapping[str, Mapping[str, Any]], result["timeframes"]).items():
        lines.append(
            "| {timeframe} | {status} | {structure} | {close} | {warnings} |".format(
                timeframe=timeframe,
                status=summary["status"],
                structure=summary.get("market_structure", "-"),
                close=_format_optional_float(summary.get("latest_close")),
                warnings=len(cast(Sequence[str], summary.get("warnings", []))),
            )
        )
    return lines


def _format_entry(value: object) -> str:
    """entry zone을 짧은 문자열로 포맷한다."""
    if not isinstance(value, Mapping):
        return "-"
    lower = value.get("lower")
    upper = value.get("upper")
    if not isinstance(lower, int | float) or not isinstance(upper, int | float):
        return "-"
    return f"{float(lower):.2f} ~ {float(upper):.2f}"


def _format_optional_float(value: object) -> str:
    """None 가능한 숫자 값을 문자열로 포맷한다."""
    if not isinstance(value, int | float):
        return "-"
    return f"{float(value):.2f}"


def _format_percent(value: float) -> str:
    """0~1 confidence를 퍼센트 문자열로 포맷한다."""
    return f"{value * 100:.1f}%"


def _default_output_path(output_format: str, now: datetime) -> Path:
    """출력 경로가 없을 때 날짜 기반 기본 경로를 만든다."""
    suffix = "md" if output_format == "markdown" else "json"
    return Path("reports") / f"smart_money_{now.strftime('%Y%m%d')}.{suffix}"


def _isoformat(value: datetime) -> str:
    """datetime을 timezone 정보가 포함된 ISO 문자열로 변환한다."""
    if value.tzinfo is None:
        return value.astimezone().isoformat()
    return value.isoformat()


def _format_exception(exc: Exception) -> str:
    """예외를 빈 문자열 없이 사용자용 메시지로 변환한다."""
    return str(exc) or exc.__class__.__name__


def _deduplicate(values: Sequence[str]) -> list[str]:
    """순서를 보존하면서 중복 문자열을 제거한다."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
