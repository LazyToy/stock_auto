from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.optimization.indicators import build_ohlcv_features


UPTREND = "uptrend"
DOWNTREND = "downtrend"
RANGE = "range"
HIGH_VOLATILITY = "high_volatility"
LOW_LIQUIDITY = "low_liquidity"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegimeConfig:
    short_window: int = 20
    long_window: int = 60
    adx_trend_threshold: float = 20.0
    min_trend_gap: float = 0.01
    high_volatility_threshold: float = 0.45
    min_relative_volume: float = 0.5


def detect_regime_series(
    df: pd.DataFrame,
    config: RegimeConfig | None = None,
) -> pd.Series:
    """Return a per-bar primary regime label for AutoML signal filtering."""
    cfg = config or RegimeConfig()
    features = build_ohlcv_features(df)
    if features.empty:
        return pd.Series(dtype=object)

    close = features["close"]
    short_ma = close.rolling(max(int(cfg.short_window), 1), min_periods=1).mean()
    long_window = max(int(cfg.long_window), 1)
    long_ma = close.rolling(long_window, min_periods=1).mean()
    trend_gap = ((short_ma - long_ma) / long_ma.replace(0.0, pd.NA)).fillna(0.0)

    regimes = pd.Series(UNKNOWN, index=features.index, dtype=object)
    ready = pd.Series(range(len(features)), index=features.index) >= (long_window - 1)

    range_mask = (trend_gap.abs() < float(cfg.min_trend_gap)) | (
        features["adx"] < float(cfg.adx_trend_threshold)
    )
    uptrend_mask = (trend_gap > 0) & ~range_mask
    downtrend_mask = (trend_gap < 0) & ~range_mask

    regimes.loc[ready & range_mask] = RANGE
    regimes.loc[ready & uptrend_mask] = UPTREND
    regimes.loc[ready & downtrend_mask] = DOWNTREND

    high_vol_mask = ready & (features["realized_volatility"] >= float(cfg.high_volatility_threshold))
    low_liquidity_mask = ready & (features["relative_volume"] <= float(cfg.min_relative_volume))
    regimes.loc[high_vol_mask] = HIGH_VOLATILITY
    regimes.loc[low_liquidity_mask] = LOW_LIQUIDITY

    return regimes


def is_trend_regime(regime: str) -> bool:
    return regime in {UPTREND, DOWNTREND}


def is_tradeable_regime(regime: str) -> bool:
    return regime not in {UNKNOWN, HIGH_VOLATILITY, LOW_LIQUIDITY}


def apply_regime_filter(
    events: pd.Series,
    regimes: pd.Series,
    strategy_type: str,
) -> pd.Series:
    """Block buy events that do not fit the detected market regime."""
    aligned_regimes = regimes.reindex(events.index).fillna(UNKNOWN)
    filtered = events.copy()
    buy_mask = filtered > 0
    sell_mask = filtered < 0
    allowed_buy_mask = _allowed_buy_mask(aligned_regimes, strategy_type)
    filtered.loc[buy_mask & ~allowed_buy_mask] = 0
    filtered.loc[sell_mask] = events.loc[sell_mask]
    return filtered.astype(int)


def _allowed_buy_mask(regimes: pd.Series, strategy_type: str) -> pd.Series:
    normalized = (strategy_type or "").strip().upper().replace(" ", "_")
    tradeable = regimes.map(is_tradeable_regime)

    if normalized in {"MA_CROSSOVER", "MACD", "MACD_RSI"}:
        return tradeable & (regimes == UPTREND)
    if normalized in {"RSI", "BOLLINGER"}:
        return tradeable & regimes.isin([RANGE, UPTREND])
    if normalized == "ENSEMBLE_VOTE":
        return tradeable & regimes.isin([RANGE, UPTREND])
    return tradeable
