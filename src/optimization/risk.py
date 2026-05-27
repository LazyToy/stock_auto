from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.optimization.indicators import build_ohlcv_features


@dataclass(frozen=True)
class RiskConfig:
    atr_stop_multiplier: float | None = None
    trailing_stop_pct: float | None = None
    max_holding_days: int | None = None
    cooldown_days: int = 0


@dataclass(frozen=True)
class SimulationResult:
    returns: np.ndarray
    trade_count: int
    position: np.ndarray
    exit_reasons: dict[str, int] = field(default_factory=dict)


def simulate_long_only_with_risk(
    df: pd.DataFrame,
    events: pd.Series,
    risk_config: RiskConfig | None = None,
    *,
    fee: float = 0.0,
    slippage: float = 0.0,
    tax: float = 0.0,
) -> SimulationResult:
    """Simulate long-only next-bar execution with optional risk exits."""
    risk = risk_config or RiskConfig()
    features = build_ohlcv_features(df)
    if features.empty:
        return SimulationResult(np.array([], dtype=float), 0, np.array([], dtype=int), {})

    close = features["close"].to_numpy(dtype=float)
    low = features["low"].to_numpy(dtype=float)
    atr = features["atr"].to_numpy(dtype=float)
    daily_returns = pd.Series(close).pct_change().fillna(0.0).to_numpy(dtype=float)
    event_values = events.reindex(features.index).fillna(0).to_numpy(dtype=int)
    strategy_returns = np.zeros_like(daily_returns)
    position_history = np.zeros(len(close), dtype=int)
    exit_reasons: dict[str, int] = {}

    position = 0
    trade_count = 0
    trade_cost = fee + slippage
    entry_price = 0.0
    peak_price = 0.0
    holding_days = 0
    cooldown_remaining = 0

    for i in range(1, len(close)):
        previous_event = event_values[i - 1]
        if position == 0:
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
            elif previous_event > 0:
                position = 1
                trade_count += 1
                entry_price = close[i]
                peak_price = close[i]
                holding_days = 0
                strategy_returns[i] = daily_returns[i] - trade_cost
        else:
            holding_days += 1
            peak_price = max(peak_price, close[i])
            strategy_returns[i] = daily_returns[i]

            exit_reason = _exit_reason(
                previous_event=previous_event,
                close_price=close[i],
                low_price=low[i],
                atr_value=atr[i],
                entry_price=entry_price,
                peak_price=peak_price,
                holding_days=holding_days,
                risk=risk,
            )
            if exit_reason is not None:
                position = 0
                trade_count += 1
                strategy_returns[i] = daily_returns[i] - trade_cost - tax
                cooldown_remaining = max(int(risk.cooldown_days), 0)
                exit_reasons[exit_reason] = exit_reasons.get(exit_reason, 0) + 1

        position_history[i] = position

    return SimulationResult(strategy_returns, trade_count, position_history, exit_reasons)


def _exit_reason(
    *,
    previous_event: int,
    close_price: float,
    low_price: float,
    atr_value: float,
    entry_price: float,
    peak_price: float,
    holding_days: int,
    risk: RiskConfig,
) -> str | None:
    if risk.atr_stop_multiplier is not None and atr_value > 0:
        stop_price = entry_price - (atr_value * float(risk.atr_stop_multiplier))
        if low_price <= stop_price:
            return "atr_stop"

    if risk.trailing_stop_pct is not None and peak_price > 0:
        trailing_floor = peak_price * (1.0 - float(risk.trailing_stop_pct))
        if low_price <= trailing_floor or close_price <= trailing_floor:
            return "trailing_stop"

    if risk.max_holding_days is not None and holding_days >= int(risk.max_holding_days):
        return "max_holding"

    if previous_event < 0:
        return "signal"

    return None
