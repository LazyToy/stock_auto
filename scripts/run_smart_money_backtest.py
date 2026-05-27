"""Smart Money 백테스트 CLI 리포트 생성기."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.timeframes import (
    MultiTimeframeDataset,
    MultiTimeframeFetcher,
    Timeframe,
    TimeframeData,
)
from src.backtest.smart_money_engine import (
    SmartMoneyBacktestConfig,
    SmartMoneyBacktestResult,
    SmartMoneyBacktestTrade,
    run_smart_money_backtest,
)

Clock = Callable[[], datetime]
ReportPayload = dict[str, Any]

DEFAULT_MARKET: str = "US"
DEFAULT_EXCHANGE: str = "NASD"
PERIOD_TO_DAYS: dict[str, int] = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 365,
    "2y": 730,
}
DEFAULT_FIXTURE_CSV_PATH: Path = (
    PROJECT_ROOT / "tests" / "fixtures" / "ohlcv" / "smart_money_backtest_tradeable.csv"
)
FIXTURE_SOURCE_NAME: str = DEFAULT_FIXTURE_CSV_PATH.name
REQUIRED_FIXTURE_COLUMNS: tuple[str, ...] = ("timestamp", "open", "high", "low", "close", "volume")


class SmartMoneyBacktestFetcher(Protocol):
    """백테스트 CLI가 요구하는 timeframe fetcher 계약."""

    def fetch_symbol(
        self,
        symbol: str,
        market: str = "KR",
        exchange: str = "NASD",
    ) -> MultiTimeframeDataset:
        """종목별 multi-timeframe OHLCV 묶음을 반환한다."""


class FixtureSmartMoneyBacktestFetcher:
    """백테스트 smoke 검증용 deterministic fixture fetcher."""

    def __init__(self, csv_path: Path = DEFAULT_FIXTURE_CSV_PATH) -> None:
        """저장 CSV fixture 경로를 설정한다."""
        self._csv_path = csv_path

    def fetch_symbol(
        self,
        symbol: str,
        market: str = "KR",
        exchange: str = "NASD",
    ) -> MultiTimeframeDataset:
        """Smart Money BUY가 발생하는 multi-timeframe OHLCV fixture를 반환한다."""
        clean_symbol = symbol.strip().upper()
        frame = _load_fixture_ohlcv_csv(self._csv_path)
        return MultiTimeframeDataset(
            symbol=clean_symbol,
            market=market.strip().upper(),
            exchange=exchange.strip().upper(),
            timeframes={
                Timeframe.MINUTE_5: TimeframeData(
                    Timeframe.MINUTE_5,
                    frame.copy(),
                    source=f"fixture-csv:{FIXTURE_SOURCE_NAME}:5m",
                ),
                Timeframe.HOUR_1: TimeframeData(
                    Timeframe.HOUR_1,
                    frame.copy(),
                    source=f"fixture-csv:{FIXTURE_SOURCE_NAME}:1h",
                ),
                Timeframe.DAY_1: TimeframeData(
                    Timeframe.DAY_1,
                    frame.copy(),
                    source=f"fixture-csv:{FIXTURE_SOURCE_NAME}:1d",
                ),
            },
        )


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 만든다."""
    parser = argparse.ArgumentParser(description="Smart Money 신호 백테스트 실행")
    parser.add_argument("--symbols", required=True, help="백테스트할 종목 목록. 예: AAPL,MSFT")
    parser.add_argument("--market", default=DEFAULT_MARKET, choices=("KR", "US"), help="시장 구분")
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE, help="거래소 코드")
    parser.add_argument(
        "--period", default="1y", help="데이터 조회 기간. 허용값: 1mo,3mo,6mo,1y,2y"
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="리포트 생성 시각을 ISO-8601 문자열로 고정합니다. 결정론적 비교용입니다.",
    )
    parser.add_argument("--capital", type=float, default=10_000_000.0, help="초기 자본")
    parser.add_argument("--commission-rate", type=float, default=0.00015, help="거래 수수료율")
    parser.add_argument("--slippage-rate", type=float, default=0.0, help="체결 슬리피지율")
    parser.add_argument("--position-size-pct", type=float, default=0.95, help="현금 대비 진입 비율")
    parser.add_argument("--max-holding-bars", type=int, default=20, help="최대 보유 캔들 수")
    parser.add_argument(
        "--min-history-bars", type=int, default=20, help="신호 계산 전 최소 캔들 수"
    )
    parser.add_argument("--output", default=None, help="리포트 출력 경로")
    parser.add_argument("--format", default="json", choices=("json", "markdown"), help="출력 형식")
    parser.add_argument(
        "--fixture", action="store_true", help="네트워크 없이 fixture 데이터로 실행"
    )
    return parser


def main(argv: Sequence[str] | None = None, *, clock: Clock | None = None) -> int:
    """CLI 진입점."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        symbols = parse_symbols(args.symbols)
        period_days = parse_period_days(args.period)
        now = (
            parse_generated_at(args.generated_at)
            if args.generated_at
            else (clock or datetime.now)()
        )
    except ValueError as exc:
        print(f"[smart-money-backtest] 입력 오류: {exc}", file=sys.stderr)
        return 2
    if not symbols:
        print("[smart-money-backtest] 백테스트할 종목을 1개 이상 입력해주세요.", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else _default_output_path(args.format, now)
    fetcher: SmartMoneyBacktestFetcher = (
        FixtureSmartMoneyBacktestFetcher()
        if args.fixture
        else MultiTimeframeFetcher(
            daily_lookback_days=period_days,
            yfinance_daily_period=args.period,
        )
    )
    payload = build_report_payload(
        symbols,
        market=args.market,
        exchange=args.exchange,
        period=args.period,
        generated_at=now,
        fetcher=fetcher,
        config=_config_from_args(args),
    )
    write_report(payload, output=output, output_format=args.format)
    return 0 if payload["summary"]["success_count"] > 0 else 1


def build_report_payload(
    symbols: Sequence[str],
    *,
    market: str,
    exchange: str,
    period: str,
    generated_at: datetime,
    fetcher: SmartMoneyBacktestFetcher,
    config: SmartMoneyBacktestConfig,
) -> ReportPayload:
    """종목별 Smart Money 백테스트 결과를 직렬화 가능한 payload로 만든다."""
    results = [
        _run_symbol_backtest(
            symbol,
            market=market,
            exchange=exchange,
            fetcher=fetcher,
            config=config,
        )
        for symbol in symbols
    ]
    success_count = sum(1 for item in results if item["status"] == "success")
    return {
        "generated_at": _isoformat(generated_at),
        "market": market,
        "exchange": exchange,
        "period": period,
        "summary": {
            "total_symbols": len(results),
            "success_count": success_count,
            "failure_count": len(results) - success_count,
        },
        "results": results,
    }


def parse_symbols(value: str) -> list[str]:
    """쉼표/줄바꿈 입력을 중복 없는 대문자 symbol 목록으로 변환한다."""
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


def parse_period_days(value: str) -> int:
    """CLI period 문자열을 일봉 lookback 일수로 변환한다."""
    if not isinstance(value, str):
        raise ValueError("period는 문자열이어야 합니다.")
    normalized = value.strip().lower()
    if normalized in PERIOD_TO_DAYS:
        return PERIOD_TO_DAYS[normalized]
    allowed = ", ".join(PERIOD_TO_DAYS)
    raise ValueError(f"지원하지 않는 period입니다: {value}. 허용값: {allowed}")


def parse_generated_at(value: str) -> datetime:
    """ISO-8601 timestamp 인자를 datetime으로 변환한다."""
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"generated-at 형식이 올바르지 않습니다: {value}") from exc


def write_report(payload: Mapping[str, Any], *, output: Path, output_format: str) -> None:
    """payload를 지정 경로에 저장한다."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return
    if output_format == "markdown":
        output.write_text(render_markdown(payload), encoding="utf-8")
        return
    raise ValueError(f"지원하지 않는 리포트 형식입니다: {output_format}")


def render_markdown(payload: Mapping[str, Any]) -> str:
    """백테스트 payload를 Markdown으로 렌더링한다."""
    lines = [
        "# Smart Money 백테스트 리포트",
        "",
        f"- 실행 시각: {payload['generated_at']}",
        f"- 시장: {payload['market']}",
        f"- 기간: {payload['period']}",
        "",
        "| symbol | status | trades | win rate | total return | max drawdown |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for result in cast(Sequence[Mapping[str, Any]], payload["results"]):
        metrics = cast(Mapping[str, Any], result.get("metrics", {}))
        lines.append(
            "| {symbol} | {status} | {trades} | {win_rate} | {total_return} | {mdd} |".format(
                symbol=result["symbol"],
                status=result["status"],
                trades=metrics.get("total_trades", 0),
                win_rate=_format_percent(metrics.get("win_rate")),
                total_return=_format_percent(result.get("total_return")),
                mdd=_format_percent(metrics.get("max_drawdown")),
            )
        )
    lines.extend(_render_trade_sections(payload))
    return "\n".join(lines) + "\n"


def _run_symbol_backtest(
    symbol: str,
    *,
    market: str,
    exchange: str,
    fetcher: SmartMoneyBacktestFetcher,
    config: SmartMoneyBacktestConfig,
) -> ReportPayload:
    """단일 종목 수집과 백테스트 실패를 격리한다."""
    try:
        dataset = fetcher.fetch_symbol(symbol, market=market, exchange=exchange)
        frames = dataset.successful_ohlcv()
        if not frames:
            raise ValueError("백테스트 가능한 timeframe 데이터가 없습니다.")
        result = run_smart_money_backtest(
            frames,
            config=SmartMoneyBacktestConfig(
                symbol=dataset.symbol,
                initial_capital=config.initial_capital,
                commission_rate=config.commission_rate,
                slippage_rate=config.slippage_rate,
                position_size_pct=config.position_size_pct,
                max_holding_bars=config.max_holding_bars,
                min_history_bars=config.min_history_bars,
            ),
        )
        return _serialize_success(dataset.symbol, result)
    except Exception as exc:
        return {"symbol": symbol, "status": "error", "error": _format_exception(exc)}


def _serialize_success(symbol: str, result: SmartMoneyBacktestResult) -> ReportPayload:
    """백테스트 성공 결과를 JSON payload로 변환한다."""
    trades = [_serialize_trade(trade) for trade in result.trades]
    return {
        "symbol": symbol,
        "status": "success",
        "initial_capital": result.initial_capital,
        "final_equity": result.final_equity,
        "total_return": result.total_return,
        "metrics": {
            "total_trades": result.metrics.total_trades,
            "win_rate": result.metrics.win_rate,
            "average_return": result.metrics.average_return,
            "max_drawdown": result.metrics.max_drawdown,
            "profit_factor": result.metrics.profit_factor,
            "signal_coverage": result.metrics.signal_coverage,
            "signal_counts": result.metrics.signal_counts,
            "signal_ratios": result.metrics.signal_ratios,
            "exit_reason_counts": _count_exit_reasons(trades),
        },
        "trades": trades,
        "warnings": result.warnings,
    }


def _serialize_trade(trade: SmartMoneyBacktestTrade) -> dict[str, Any]:
    """거래 기록을 JSON 직렬화 가능한 dict로 변환한다."""
    return {
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "quantity": trade.quantity,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "net_pnl": trade.net_pnl,
        "return_pct": trade.return_pct,
        "holding_bars": trade.holding_bars,
        "exit_reason": trade.exit_reason,
    }


def _count_exit_reasons(trades: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """거래별 exit_reason 분포를 계산한다."""
    counts: dict[str, int] = {}
    for trade in trades:
        reason = str(trade.get("exit_reason", "UNKNOWN"))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _render_trade_sections(payload: Mapping[str, Any]) -> list[str]:
    """Markdown 상세 거래 섹션을 만든다."""
    lines: list[str] = []
    for result in cast(Sequence[Mapping[str, Any]], payload["results"]):
        trades = cast(Sequence[Mapping[str, Any]], result.get("trades", []))
        if not trades:
            continue
        lines.extend(["", f"## {result['symbol']} trades", "", "| entry | exit | reason | pnl |"])
        lines.append("|---|---|---|---:|")
        for trade in trades:
            lines.append(
                "| {entry} | {exit} | {reason} | {pnl:.2f} |".format(
                    entry=trade["entry_time"],
                    exit=trade["exit_time"],
                    reason=trade["exit_reason"],
                    pnl=float(trade["net_pnl"]),
                )
            )
    return lines


def _config_from_args(args: argparse.Namespace) -> SmartMoneyBacktestConfig:
    """CLI 인자를 백테스트 설정으로 변환한다."""
    return SmartMoneyBacktestConfig(
        initial_capital=args.capital,
        commission_rate=args.commission_rate,
        slippage_rate=args.slippage_rate,
        position_size_pct=args.position_size_pct,
        max_holding_bars=args.max_holding_bars,
        min_history_bars=args.min_history_bars,
    )


def _load_fixture_ohlcv_csv(csv_path: Path) -> pd.DataFrame:
    """저장 CSV fixture를 표준 OHLCV DataFrame으로 읽는다."""
    try:
        raw = pd.read_csv(csv_path, parse_dates=["timestamp"])
    except FileNotFoundError as exc:
        raise ValueError(f"fixture CSV 파일을 찾을 수 없습니다: {csv_path}") from exc
    except Exception as exc:
        raise ValueError(f"fixture CSV 파일을 읽을 수 없습니다: {csv_path}: {exc}") from exc

    missing = [column for column in REQUIRED_FIXTURE_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(f"fixture CSV 필수 컬럼이 없습니다: {', '.join(missing)}")
    frame = raw.loc[:, list(REQUIRED_FIXTURE_COLUMNS)].set_index("timestamp")
    frame.index = pd.DatetimeIndex(frame.index)
    return cast(pd.DataFrame, frame.astype(float))


def _default_output_path(output_format: str, now: datetime) -> Path:
    """출력 경로가 없을 때 날짜 기반 기본 경로를 만든다."""
    suffix = "md" if output_format == "markdown" else "json"
    return Path("reports") / f"smart_money_backtest_{now.strftime('%Y%m%d')}.{suffix}"


def _isoformat(value: datetime) -> str:
    """datetime을 ISO 문자열로 변환한다."""
    if value.tzinfo is None:
        return value.astimezone().isoformat()
    return value.isoformat()


def _format_percent(value: object) -> str:
    """0~1 비율을 퍼센트 문자열로 표시한다."""
    if not isinstance(value, int | float):
        return "-"
    return f"{float(value) * 100:.2f}%"


def _format_exception(exc: Exception) -> str:
    """예외를 빈 문자열 없이 사용자용 메시지로 변환한다."""
    return str(exc) or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
