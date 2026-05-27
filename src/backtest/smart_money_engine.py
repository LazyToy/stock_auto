"""Smart Money 신호 전용 walk-forward 백테스트 엔진."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src.analysis.ohlcv import normalize_ohlcv_frame, validate_ohlcv_frame
from src.analysis.smart_money import (
    SignalConfig,
    SmartMoneySignal,
    analyze_multi_timeframe_patterns,
    combine_multi_timeframe_signals,
)

BUY_SIGNAL = "BUY"
SELL_SIGNAL = "SELL"
HOLD_SIGNAL = "HOLD"
INVALIDATION_EXIT = "INVALIDATION"
SELL_SIGNAL_EXIT = "SELL_SIGNAL"
MAX_HOLD_EXIT = "MAX_HOLDING_BARS"
END_OF_DATA_EXIT = "END_OF_DATA"

_REQUIRED_EXECUTION_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
_TIMEFRAME_ALIASES: dict[str, str] = {
    "5m": "5m",
    "5min": "5m",
    "minute_5": "5m",
    "1h": "1h",
    "60m": "1h",
    "hourly": "1h",
    "1d": "1d",
    "daily": "1d",
}


@dataclass(frozen=True)
class SmartMoneyBacktestConfig:
    """Smart Money 백테스트 실행 설정."""

    symbol: str = "UNKNOWN"
    initial_capital: float = 10_000_000.0
    commission_rate: float = 0.00015
    slippage_rate: float = 0.0
    position_size_pct: float = 0.95
    max_holding_bars: int = 20
    min_history_bars: int = 20
    execution_timeframe: str = "5m"
    signal_config: SignalConfig = field(default_factory=SignalConfig)
    raise_on_signal_error: bool = False


@dataclass(frozen=True)
class SmartMoneyBacktestTrade:
    """완료된 단일 long 거래 기록."""

    symbol: str
    entry_time: datetime
    exit_time: datetime
    quantity: int
    entry_price: float
    exit_price: float
    entry_commission: float
    exit_commission: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    holding_bars: int
    exit_reason: str


@dataclass(frozen=True)
class SmartMoneyBacktestMetrics:
    """백테스트 성능 지표."""

    total_trades: int
    win_rate: float
    average_return: float
    max_drawdown: float
    profit_factor: float
    signal_coverage: float
    signal_counts: dict[str, int]
    signal_ratios: dict[str, float]


@dataclass(frozen=True)
class SmartMoneyBacktestResult:
    """Smart Money 백테스트 최종 결과."""

    symbol: str
    initial_capital: float
    final_equity: float
    total_return: float
    trades: list[SmartMoneyBacktestTrade]
    equity_curve: pd.DataFrame
    metrics: SmartMoneyBacktestMetrics
    signal_history: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


@dataclass
class _OpenPosition:
    """엔진 내부 long 포지션 상태."""

    quantity: int
    entry_price: float
    entry_time: datetime
    entry_bar_index: int
    entry_commission: float
    entry_cost: float
    invalidation_level: float | None


@dataclass(frozen=True)
class _PendingOrder:
    """다음 캔들 open에 실행할 주문."""

    side: str
    signal: SmartMoneySignal


SignalResolver = Callable[[Mapping[str, pd.DataFrame], SignalConfig], SmartMoneySignal]


class SmartMoneyBacktestEngine:
    """Smart Money 신호를 long-only 방식으로 walk-forward 검증한다."""

    def __init__(
        self,
        dataset: Mapping[str, pd.DataFrame],
        *,
        config: SmartMoneyBacktestConfig | None = None,
        signal_resolver: SignalResolver | None = None,
    ) -> None:
        """데이터와 설정을 검증하고 엔진 상태를 초기화한다."""
        self.config = config or SmartMoneyBacktestConfig()
        _validate_config(self.config)
        self.frames = _normalize_dataset(dataset)
        self.execution_frame = _select_execution_frame(self.frames, self.config.execution_timeframe)
        self.signal_resolver = signal_resolver or _resolve_signal
        self.cash = float(self.config.initial_capital)
        self.position: _OpenPosition | None = None
        self.trades: list[SmartMoneyBacktestTrade] = []
        self.warnings: list[str] = []
        self._equity_rows: list[dict[str, object]] = []
        self._signal_rows: list[dict[str, object]] = []

    def run(self) -> SmartMoneyBacktestResult:
        """전체 구간을 순회하며 백테스트를 실행한다."""
        pending: _PendingOrder | None = None
        for bar_index, (timestamp, row) in enumerate(self.execution_frame.iterrows()):
            current_time = _as_datetime(timestamp)
            pending = self._execute_pending_order(pending, bar_index, current_time, row)
            if self.position is not None:
                self._check_position_exit(bar_index, current_time, row)
            signal = self._build_signal(bar_index, current_time)
            pending = self._stage_next_order(signal, pending)
            self._record_equity(current_time, row)
        closed_at_end = self._close_open_position_at_end()
        if closed_at_end and self._equity_rows:
            self._equity_rows[-1]["equity"] = self.cash
            self._equity_rows[-1]["cash"] = self.cash
            self._equity_rows[-1]["position_quantity"] = 0
        equity_curve = pd.DataFrame(self._equity_rows).set_index("timestamp")
        signal_history = pd.DataFrame(self._signal_rows).set_index("timestamp")
        final_equity = self._current_equity(self.execution_frame.iloc[-1])
        return SmartMoneyBacktestResult(
            symbol=self.config.symbol,
            initial_capital=self.config.initial_capital,
            final_equity=final_equity,
            total_return=_safe_div(
                final_equity - self.config.initial_capital, self.config.initial_capital
            ),
            trades=list(self.trades),
            equity_curve=equity_curve,
            metrics=_calculate_metrics(self.trades, equity_curve, signal_history),
            signal_history=signal_history,
            warnings=list(self.warnings),
        )

    def _execute_pending_order(
        self,
        pending: _PendingOrder | None,
        bar_index: int,
        timestamp: datetime,
        row: pd.Series,
    ) -> _PendingOrder | None:
        """직전 캔들에서 생성된 주문을 현재 캔들 open에 실행한다."""
        if pending is None:
            return None
        if pending.side == BUY_SIGNAL and self.position is None:
            self._enter_long(bar_index, timestamp, row, pending.signal)
        elif pending.side == SELL_SIGNAL and self.position is not None:
            self._exit_long(bar_index, timestamp, row, _sell_price(row), SELL_SIGNAL_EXIT)
        return None

    def _build_signal(self, bar_index: int, timestamp: datetime) -> SmartMoneySignal:
        """현재 시점까지의 과거 데이터만 사용해 Smart Money 신호를 만든다."""
        if bar_index + 1 < self.config.min_history_bars:
            signal = _hold_signal("데이터가 최소 분석 구간보다 부족합니다.")
        else:
            signal = self._resolve_window_signal(timestamp)
        self._signal_rows.append(
            {
                "timestamp": timestamp,
                "signal": signal.signal,
                "confidence": signal.confidence,
                "score": signal.score,
                "invalidation_level": signal.invalidation_level,
            }
        )
        return signal

    def _resolve_window_signal(self, timestamp: datetime) -> SmartMoneySignal:
        """timeframe별 walk-forward window를 만들어 signal resolver를 호출한다."""
        windows = {
            timeframe: frame.loc[frame.index <= timestamp].copy()
            for timeframe, frame in self.frames.items()
        }
        try:
            return self.signal_resolver(windows, self.config.signal_config)
        except Exception as exc:
            if self.config.raise_on_signal_error:
                raise
            message = f"Smart Money 신호 계산 실패: {_format_exception(exc)}"
            self.warnings.append(message)
            return _hold_signal(message)

    def _stage_next_order(
        self,
        signal: SmartMoneySignal,
        pending: _PendingOrder | None,
    ) -> _PendingOrder | None:
        """현재 신호를 다음 캔들 주문으로 예약한다."""
        if pending is not None:
            return pending
        if signal.signal == BUY_SIGNAL and self.position is None:
            return _PendingOrder(BUY_SIGNAL, signal)
        if signal.signal == SELL_SIGNAL and self.position is not None:
            return _PendingOrder(SELL_SIGNAL, signal)
        return None

    def _enter_long(
        self,
        bar_index: int,
        timestamp: datetime,
        row: pd.Series,
        signal: SmartMoneySignal,
    ) -> None:
        """현금 한도 안에서 long 포지션을 진입한다."""
        entry_price = _buy_price(row, self.config.slippage_rate)
        budget = self.cash * self.config.position_size_pct
        quantity = int(budget // (entry_price * (1.0 + self.config.commission_rate)))
        if quantity <= 0:
            self.warnings.append("매수 가능 수량이 0이라 진입을 건너뜁니다.")
            return
        entry_notional = quantity * entry_price
        commission = entry_notional * self.config.commission_rate
        self.cash -= entry_notional + commission
        self.position = _OpenPosition(
            quantity=quantity,
            entry_price=entry_price,
            entry_time=timestamp,
            entry_bar_index=bar_index,
            entry_commission=commission,
            entry_cost=entry_notional + commission,
            invalidation_level=signal.invalidation_level,
        )

    def _check_position_exit(self, bar_index: int, timestamp: datetime, row: pd.Series) -> None:
        """invalidation 또는 최대 보유 기간 도달 여부를 확인한다."""
        position = self.position
        if position is None:
            return
        if (
            position.invalidation_level is not None
            and float(row["low"]) <= position.invalidation_level
        ):
            self._exit_long(
                bar_index, timestamp, row, position.invalidation_level, INVALIDATION_EXIT
            )
            return
        if bar_index - position.entry_bar_index >= self.config.max_holding_bars:
            self._exit_long(bar_index, timestamp, row, _sell_price(row), MAX_HOLD_EXIT)

    def _exit_long(
        self,
        bar_index: int,
        timestamp: datetime,
        row: pd.Series,
        raw_exit_price: float,
        reason: str,
    ) -> None:
        """현재 long 포지션을 청산하고 거래 기록을 남긴다."""
        position = self.position
        if position is None:
            return
        exit_price = _apply_sell_slippage(raw_exit_price, self.config.slippage_rate)
        exit_notional = position.quantity * exit_price
        exit_commission = exit_notional * self.config.commission_rate
        proceeds = exit_notional - exit_commission
        self.cash += proceeds
        gross_pnl = (exit_price - position.entry_price) * position.quantity
        net_pnl = proceeds - position.entry_cost
        self.trades.append(
            SmartMoneyBacktestTrade(
                symbol=self.config.symbol,
                entry_time=position.entry_time,
                exit_time=timestamp,
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=exit_price,
                entry_commission=position.entry_commission,
                exit_commission=exit_commission,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_pct=_safe_div(net_pnl, position.entry_cost),
                holding_bars=bar_index - position.entry_bar_index,
                exit_reason=reason,
            )
        )
        self.position = None

    def _record_equity(self, timestamp: datetime, row: pd.Series) -> None:
        """현재 캔들 종가 기준 평가 자산을 기록한다."""
        self._equity_rows.append(
            {
                "timestamp": timestamp,
                "equity": self._current_equity(row),
                "cash": self.cash,
                "position_quantity": self.position.quantity if self.position else 0,
            }
        )

    def _current_equity(self, row: pd.Series) -> float:
        """현금과 보유 포지션 평가액을 합산한다."""
        if self.position is None:
            return self.cash
        return self.cash + self.position.quantity * float(row["close"])

    def _close_open_position_at_end(self) -> bool:
        """데이터 종료 시점에 남은 포지션을 종가 기준으로 청산한다."""
        if self.position is None:
            return False
        last_index = len(self.execution_frame) - 1
        timestamp, row = next(iter(self.execution_frame.iloc[[-1]].iterrows()))
        self._exit_long(
            last_index, _as_datetime(timestamp), row, float(row["close"]), END_OF_DATA_EXIT
        )
        return True


def run_smart_money_backtest(
    dataset: Mapping[str, pd.DataFrame],
    *,
    config: SmartMoneyBacktestConfig | None = None,
    signal_resolver: SignalResolver | None = None,
) -> SmartMoneyBacktestResult:
    """Smart Money 백테스트를 함수형 API로 실행한다."""
    return SmartMoneyBacktestEngine(
        dataset,
        config=config,
        signal_resolver=signal_resolver,
    ).run()


def _resolve_signal(
    windows: Mapping[str, pd.DataFrame],
    signal_config: SignalConfig,
) -> SmartMoneySignal:
    """기존 Smart Money public API로 현재 window의 최종 신호를 계산한다."""
    reports = analyze_multi_timeframe_patterns(windows)
    return combine_multi_timeframe_signals(reports, signal_config)


def _normalize_dataset(dataset: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """입력 dataset을 표준 timeframe key와 OHLCV 계약으로 정규화한다."""
    if dataset is None:
        raise ValueError("dataset이 None입니다. timeframe별 OHLCV DataFrame을 전달해주세요.")
    frames: dict[str, pd.DataFrame] = {}
    for timeframe, frame in dataset.items():
        key = _canonical_timeframe(timeframe)
        normalized = normalize_ohlcv_frame(frame)
        is_valid, errors = validate_ohlcv_frame(normalized)
        if not is_valid:
            raise ValueError(f"{key} OHLCV 검증 실패: {', '.join(errors)}")
        frames[key] = normalized.loc[:, list(_REQUIRED_EXECUTION_COLUMNS)].copy()
    if not frames:
        raise ValueError("dataset이 비어 있습니다. 최소 1개 timeframe이 필요합니다.")
    return frames


def _select_execution_frame(
    frames: Mapping[str, pd.DataFrame],
    execution_timeframe: str,
) -> pd.DataFrame:
    """체결 기준 timeframe을 선택한다."""
    key = _canonical_timeframe(execution_timeframe)
    if key in frames:
        frame = frames[key]
    else:
        frame = next(iter(frames.values()))
    if len(frame) == 0:
        raise ValueError("체결 기준 OHLCV DataFrame이 비어 있습니다.")
    return frame


def _validate_config(config: SmartMoneyBacktestConfig) -> None:
    """백테스트 설정값의 타입과 범위를 검증한다."""
    if config.initial_capital <= 0:
        raise ValueError("initial_capital은 0보다 커야 합니다.")
    if not 0.0 <= config.commission_rate < 1.0:
        raise ValueError("commission_rate는 0 이상 1 미만이어야 합니다.")
    if not 0.0 <= config.slippage_rate < 1.0:
        raise ValueError("slippage_rate는 0 이상 1 미만이어야 합니다.")
    if not 0.0 < config.position_size_pct <= 1.0:
        raise ValueError("position_size_pct는 0보다 크고 1 이하여야 합니다.")
    if config.max_holding_bars < 1:
        raise ValueError("max_holding_bars는 1 이상이어야 합니다.")
    if config.min_history_bars < 1:
        raise ValueError("min_history_bars는 1 이상이어야 합니다.")


def _calculate_metrics(
    trades: list[SmartMoneyBacktestTrade],
    equity_curve: pd.DataFrame,
    signal_history: pd.DataFrame,
) -> SmartMoneyBacktestMetrics:
    """거래 목록과 equity curve에서 성능 지표를 계산한다."""
    signal_counts = _signal_counts(signal_history)
    total_signals = sum(signal_counts.values())
    non_hold_signals = signal_counts[BUY_SIGNAL] + signal_counts[SELL_SIGNAL]
    returns = [trade.return_pct for trade in trades]
    wins = [trade for trade in trades if trade.net_pnl > 0]
    gross_profit = sum(trade.net_pnl for trade in trades if trade.net_pnl > 0)
    gross_loss = abs(sum(trade.net_pnl for trade in trades if trade.net_pnl < 0))
    return SmartMoneyBacktestMetrics(
        total_trades=len(trades),
        win_rate=_safe_div(len(wins), len(trades)),
        average_return=sum(returns) / len(returns) if returns else 0.0,
        max_drawdown=_calculate_max_drawdown(equity_curve),
        profit_factor=_profit_factor(gross_profit, gross_loss),
        signal_coverage=_safe_div(non_hold_signals, total_signals),
        signal_counts=signal_counts,
        signal_ratios={
            signal: _safe_div(count, total_signals) for signal, count in signal_counts.items()
        },
    )


def _signal_counts(signal_history: pd.DataFrame) -> dict[str, int]:
    """BUY/SELL/HOLD 신호 개수를 고정된 key로 반환한다."""
    counts = {BUY_SIGNAL: 0, SELL_SIGNAL: 0, HOLD_SIGNAL: 0}
    if "signal" not in signal_history.columns:
        return counts
    for value in signal_history["signal"]:
        signal = str(value)
        counts[signal if signal in counts else HOLD_SIGNAL] += 1
    return counts


def _calculate_max_drawdown(equity_curve: pd.DataFrame) -> float:
    """equity curve에서 최대 낙폭을 0~1 비율로 계산한다."""
    if equity_curve.empty or "equity" not in equity_curve.columns:
        return 0.0
    rolling_max = equity_curve["equity"].cummax()
    drawdowns = equity_curve["equity"] / rolling_max - 1.0
    return abs(float(drawdowns.min()))


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    """profit factor를 계산한다."""
    if gross_loss == 0.0:
        return float("inf") if gross_profit > 0.0 else 0.0
    return gross_profit / gross_loss


def _canonical_timeframe(timeframe: object) -> str:
    """timeframe alias를 표준 key로 변환한다."""
    if not isinstance(timeframe, str):
        raise ValueError("timeframe key는 문자열이어야 합니다.")
    key = timeframe.strip().lower()
    if not key:
        raise ValueError("timeframe key가 비어 있습니다.")
    return _TIMEFRAME_ALIASES.get(key, key)


def _hold_signal(reason: str) -> SmartMoneySignal:
    """백테스트 내부 HOLD 신호를 생성한다."""
    return SmartMoneySignal(
        signal=HOLD_SIGNAL,
        confidence=0.0,
        score=0.0,
        risk_level="HIGH",
        reasons=[reason],
    )


def _buy_price(row: pd.Series, slippage_rate: float) -> float:
    """매수 체결가에 슬리피지를 반영한다."""
    return float(row["open"]) * (1.0 + slippage_rate)


def _sell_price(row: pd.Series) -> float:
    """매도 기준 가격으로 현재 캔들 open을 사용한다."""
    return float(row["open"])


def _apply_sell_slippage(price: float, slippage_rate: float) -> float:
    """매도 체결가에 슬리피지를 반영한다."""
    return float(price) * (1.0 - slippage_rate)


def _safe_div(numerator: float, denominator: float) -> float:
    """0 나눗셈을 0.0으로 방어한다."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _as_datetime(value: object) -> datetime:
    """pandas Timestamp 또는 datetime-like 값을 datetime으로 변환한다."""
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return pd.Timestamp(str(value)).to_pydatetime()


def _format_exception(exc: Exception) -> str:
    """예외를 빈 문자열 없이 사용자용 메시지로 변환한다."""
    return str(exc) or exc.__class__.__name__


__all__ = [
    "SmartMoneyBacktestConfig",
    "SmartMoneyBacktestEngine",
    "SmartMoneyBacktestMetrics",
    "SmartMoneyBacktestResult",
    "SmartMoneyBacktestTrade",
    "run_smart_money_backtest",
]
