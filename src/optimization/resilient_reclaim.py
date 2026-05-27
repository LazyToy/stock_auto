"""Feature and signal helpers for Resilient Reclaim research."""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.optimization.indicators import build_ohlcv_features
from src.optimization.risk import RiskConfig, simulate_long_only_with_risk


_EXIT_REASON_KEYS = ["signal", "atr_stop", "trailing_stop", "max_holding"]


def build_resilient_reclaim_features(
    df: pd.DataFrame,
    *,
    benchmark: pd.DataFrame | pd.Series | None = None,
    sector: pd.DataFrame | pd.Series | None = None,
    high_window: int = 252,
    momentum_window: int = 63,
    beta_window: int = 63,
    max_factor_ffill_days: int | None = 5,
) -> pd.DataFrame:
    """Build shifted 52-week high and residual momentum research features."""
    features = build_ohlcv_features(df)
    if features.empty:
        return features

    close = features["close"]
    high_window = max(int(high_window), 1)
    momentum_window = max(int(momentum_window), 1)
    beta_window = max(int(beta_window), 2)

    previous_high = features["high"].shift(1).rolling(high_window, min_periods=1).max()
    features["high_52w_previous"] = previous_high
    features["high_52w_proximity"] = (close / previous_high.replace(0.0, np.nan)).replace(
        [np.inf, -np.inf],
        np.nan,
    )
    features["asset_momentum"] = close.pct_change(momentum_window, fill_method=None)

    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    residual_returns = asset_returns.copy()
    valid_factor_mask = pd.Series(True, index=features.index)

    benchmark_close = _aligned_close(
        benchmark,
        close.index,
        max_ffill_days=max_factor_ffill_days,
    )
    if benchmark_close is not None:
        valid_factor_mask &= benchmark_close.notna()
        benchmark_returns = benchmark_close.pct_change(fill_method=None).fillna(0.0)
        benchmark_beta = _rolling_beta(asset_returns, benchmark_returns, beta_window)
        market_residual_returns = asset_returns - benchmark_returns.mul(benchmark_beta)
        features["benchmark_momentum"] = benchmark_close.pct_change(momentum_window, fill_method=None)
        features["benchmark_close"] = benchmark_close
        features["benchmark_beta"] = benchmark_beta
    else:
        market_residual_returns = asset_returns
        features["benchmark_momentum"] = 0.0
        features["benchmark_close"] = np.nan
        features["benchmark_beta"] = 0.0

    features["market_residual_momentum"] = (
        market_residual_returns.rolling(momentum_window, min_periods=1).sum().fillna(0.0)
    )
    residual_returns = market_residual_returns.copy()

    sector_close = _aligned_close(
        sector,
        close.index,
        max_ffill_days=max_factor_ffill_days,
    )
    if sector_close is not None:
        valid_factor_mask &= sector_close.notna()
        sector_returns = sector_close.pct_change(fill_method=None).fillna(0.0)
        if benchmark_close is not None:
            sector_benchmark_beta = _rolling_beta(sector_returns, benchmark_returns, beta_window)
            sector_factor_returns = sector_returns - benchmark_returns.mul(sector_benchmark_beta)
        else:
            sector_factor_returns = sector_returns
        sector_beta = _rolling_beta(market_residual_returns, sector_factor_returns, beta_window)
        residual_returns = market_residual_returns - sector_factor_returns.mul(sector_beta)
        features["sector_momentum"] = sector_close.pct_change(momentum_window, fill_method=None)
        features["sector_close"] = sector_close
        features["sector_residual_momentum"] = (
            sector_factor_returns.rolling(momentum_window, min_periods=1).sum().fillna(0.0)
        )
        features["sector_beta"] = sector_beta
    else:
        features["sector_momentum"] = 0.0
        features["sector_close"] = np.nan
        features["sector_residual_momentum"] = 0.0
        features["sector_beta"] = 0.0

    features["residual_momentum"] = (
        residual_returns.rolling(momentum_window, min_periods=1).sum().fillna(0.0)
    )
    features.loc[~valid_factor_mask, "residual_momentum"] = np.nan
    return features


def generate_reclaim_events(
    features: pd.DataFrame,
    *,
    proximity_threshold: float = 0.97,
    reclaim_lookback: int = 20,
    min_residual_momentum: float = 0.0,
    failure_buffer: float = 0.97,
) -> pd.Series:
    """Generate buy/sell events for a shifted-high reclaim setup."""
    if features is None or features.empty:
        return pd.Series(dtype=int)

    close = pd.to_numeric(features["close"], errors="coerce")
    residual_momentum = pd.to_numeric(features["residual_momentum"], errors="coerce")
    proximity = pd.to_numeric(features["high_52w_proximity"], errors="coerce")
    reclaim_lookback = max(int(reclaim_lookback), 1)
    prior_reclaim_high = close.shift(1).rolling(reclaim_lookback, min_periods=1).max()

    buy = (
        (proximity >= float(proximity_threshold))
        & (residual_momentum >= float(min_residual_momentum))
        & (close > prior_reclaim_high)
        & (close.shift(1) < prior_reclaim_high)
    )
    events = pd.Series(0, index=features.index, dtype=int)
    in_position = False
    entry_reclaim_level = 0.0
    for timestamp in features.index:
        if not in_position:
            if bool(buy.loc[timestamp]):
                events.loc[timestamp] = 1
                in_position = True
                entry_reclaim_level = float(prior_reclaim_high.loc[timestamp])
            continue
        entry_level_failure = close.loc[timestamp] < entry_reclaim_level * float(failure_buffer)
        momentum_failure = residual_momentum.loc[timestamp] < -abs(float(min_residual_momentum))
        if bool(entry_level_failure or momentum_failure):
            events.loc[timestamp] = -1
            in_position = False
            entry_reclaim_level = 0.0
    return events


def build_failure_to_fall_filter(
    features: pd.DataFrame,
    *,
    factor_column: str = "benchmark_close",
    lookback: int = 10,
    min_factor_drawdown: float = 0.02,
    max_asset_drawdown: float = 0.05,
    min_relative_return: float = 0.0,
) -> pd.Series:
    """Return dates where the asset held up while a factor recently fell."""
    if features is None or features.empty:
        return pd.Series(dtype=bool)
    if "close" not in features.columns or factor_column not in features.columns:
        return pd.Series(False, index=features.index, dtype=bool)

    lookback = max(int(lookback), 1)
    close = pd.to_numeric(features["close"], errors="coerce")
    factor = pd.to_numeric(features[factor_column], errors="coerce")

    asset_peak = close.rolling(lookback, min_periods=1).max()
    factor_peak = factor.rolling(lookback, min_periods=1).max()
    asset_drawdown = close / asset_peak.replace(0.0, np.nan) - 1.0
    factor_drawdown = factor / factor_peak.replace(0.0, np.nan) - 1.0
    relative_return = close.pct_change(lookback, fill_method=None) - factor.pct_change(
        lookback,
        fill_method=None,
    )

    mask = (
        factor.notna()
        & close.notna()
        & (factor_drawdown <= -abs(float(min_factor_drawdown)))
        & (asset_drawdown >= -abs(float(max_asset_drawdown)))
        & (relative_return >= float(min_relative_return))
    )
    return mask.fillna(False).astype(bool)


def apply_failure_to_fall_filter(
    events: pd.Series,
    filter_mask: pd.Series,
) -> pd.Series:
    """Remove buy events that do not pass the Failure-To-Fall filter."""
    if events is None or events.empty:
        return pd.Series(dtype=int)

    filtered = events.copy().astype(int)
    aligned_mask = filter_mask.reindex(filtered.index).fillna(False).astype(bool)
    blocked_buy = (filtered > 0) & ~aligned_mask
    filtered.loc[blocked_buy] = 0
    return filtered


def compare_failure_to_fall_filter(
    df: pd.DataFrame,
    features: pd.DataFrame,
    events: pd.Series,
    *,
    factor_column: str = "benchmark_close",
    lookback: int = 10,
    min_factor_drawdown: float = 0.02,
    max_asset_drawdown: float = 0.05,
    min_relative_return: float = 0.0,
    risk_config: RiskConfig | None = None,
    fee: float = 0.0,
    slippage: float = 0.0,
    tax: float = 0.0,
) -> dict[str, object]:
    """Compare base events against a Failure-To-Fall filtered variant."""
    mask = build_failure_to_fall_filter(
        features,
        factor_column=factor_column,
        lookback=lookback,
        min_factor_drawdown=min_factor_drawdown,
        max_asset_drawdown=max_asset_drawdown,
        min_relative_return=min_relative_return,
    )
    filtered = apply_failure_to_fall_filter(events, mask)
    buys = events.reindex(mask.index).fillna(0).astype(int) > 0
    passed_buy_count = int((buys & mask).sum())
    blocked_buy_count = int((buys & ~mask).sum())
    common_kwargs = {
        "risk_config": risk_config,
        "fee": fee,
        "slippage": slippage,
        "tax": tax,
    }
    return {
        "passed_buy_count": passed_buy_count,
        "blocked_buy_count": blocked_buy_count,
        "base": evaluate_signal_events(df, events, **common_kwargs),
        "filtered": evaluate_signal_events(df, filtered, **common_kwargs),
    }


def evaluate_signal_events(
    df: pd.DataFrame,
    events: pd.Series,
    *,
    risk_config: RiskConfig | None = None,
    fee: float = 0.0,
    slippage: float = 0.0,
    tax: float = 0.0,
) -> dict[str, float]:
    """Evaluate pre-built signal events without running the AutoML optimizer."""
    features = build_ohlcv_features(df)
    if features.empty:
        return _empty_event_metrics()

    simulation = simulate_long_only_with_risk(
        df,
        events,
        risk_config or RiskConfig(),
        fee=fee,
        slippage=slippage,
        tax=tax,
    )
    return _calculate_event_metrics(
        features["close"],
        simulation.returns,
        simulation.trade_count,
        simulation.exit_reasons,
    )


def compare_atr_stop_variants(
    df: pd.DataFrame,
    events: pd.Series,
    *,
    multipliers: Iterable[float] = (1.5, 2.0, 3.0),
    include_no_stop: bool = True,
    base_risk_config: RiskConfig | None = None,
    fee: float = 0.0,
    slippage: float = 0.0,
    tax: float = 0.0,
) -> list[dict[str, float | str | None]]:
    """Evaluate the same events with multiple ATR stop multipliers."""
    base = base_risk_config or RiskConfig()
    variant_values: list[float | None] = []
    if include_no_stop:
        variant_values.append(None)
    for value in multipliers:
        variant_values.append(float(value))

    results: list[dict[str, float | str | None]] = []
    for multiplier in variant_values:
        risk = replace(base, atr_stop_multiplier=multiplier)
        metrics = evaluate_signal_events(
            df,
            events,
            risk_config=risk,
            fee=fee,
            slippage=slippage,
            tax=tax,
        )
        results.append(
            {
                "variant": _atr_variant_name(multiplier),
                "atr_stop_multiplier": multiplier,
                **metrics,
            }
        )
    return results


def _aligned_close(
    value: pd.DataFrame | pd.Series | None,
    index: pd.Index,
    *,
    max_ffill_days: int | None,
) -> pd.Series | None:
    if value is None:
        return None
    if isinstance(value, pd.Series):
        close = value
    elif "Close" in value.columns:
        close = value["Close"]
    elif "close" in value.columns:
        close = value["close"]
    else:
        return None
    numeric = pd.to_numeric(close, errors="coerce").reindex(index)
    if max_ffill_days is None:
        return numeric.ffill().astype(float)
    limit = max(int(max_ffill_days), 0)
    return numeric.ffill(limit=limit).astype(float)


def _rolling_beta(asset_returns: pd.Series, factor_returns: pd.Series, window: int) -> pd.Series:
    variance = factor_returns.rolling(window, min_periods=2).var()
    covariance = asset_returns.rolling(window, min_periods=2).cov(factor_returns)
    beta = covariance / variance.replace(0.0, np.nan)
    return beta.replace([np.inf, -np.inf], np.nan).fillna(1.0).clip(-3.0, 3.0)


def _calculate_event_metrics(
    close: pd.Series,
    strategy_returns: np.ndarray,
    trade_count: int,
    exit_reasons: dict[str, int],
) -> dict[str, float]:
    if len(strategy_returns) == 0:
        return _empty_event_metrics()

    mean_ret = float(np.mean(strategy_returns))
    std_ret = float(np.std(strategy_returns))
    sharpe = 0.0 if std_ret == 0 else float((mean_ret / std_ret) * np.sqrt(252))
    equity = np.cumprod(1 + strategy_returns)
    peak = np.maximum.accumulate(equity)
    drawdown = np.divide(equity, peak, out=np.ones_like(equity), where=peak != 0) - 1.0
    total_return = float(equity[-1] - 1.0) if len(equity) else 0.0
    benchmark_return = float(close.iloc[-1] / close.iloc[0] - 1.0) if len(close) > 1 else 0.0
    positive = strategy_returns[strategy_returns > 0].sum()
    negative = strategy_returns[strategy_returns < 0].sum()
    profit_factor = float(positive / abs(negative)) if negative < 0 else 0.0
    metrics = {
        "sharpe": sharpe,
        "total_return": total_return,
        "annual_return": (
            float((1 + total_return) ** (252 / max(len(strategy_returns), 1)) - 1)
            if total_return > -1
            else -1.0
        ),
        "benchmark_return": benchmark_return,
        "excess_return": total_return - benchmark_return,
        "max_drawdown": float(np.min(drawdown)) if len(drawdown) else 0.0,
        "profit_factor": profit_factor,
        "trade_count": float(trade_count),
        "turnover": float(trade_count / max(len(strategy_returns), 1)),
    }
    metrics.update(_exit_reason_metrics(exit_reasons))
    return metrics


def _empty_event_metrics() -> dict[str, float]:
    return {
        "sharpe": 0.0,
        "total_return": 0.0,
        "annual_return": 0.0,
        "benchmark_return": 0.0,
        "excess_return": 0.0,
        "max_drawdown": 0.0,
        "profit_factor": 0.0,
        "trade_count": 0.0,
        "turnover": 0.0,
        **_exit_reason_metrics({}),
    }


def _exit_reason_metrics(exit_reasons: dict[str, int]) -> dict[str, float]:
    return {
        f"{reason}_exit_count": float(exit_reasons.get(reason, 0))
        for reason in _EXIT_REASON_KEYS
    }


def _atr_variant_name(multiplier: float | None) -> str:
    if multiplier is None:
        return "no_atr_stop"
    if float(multiplier).is_integer():
        return f"atr_stop_{int(multiplier)}"
    return f"atr_stop_{float(multiplier):g}"
