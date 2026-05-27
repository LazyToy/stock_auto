import numpy as np
import pandas as pd

from src.optimization.regime import (
    DOWNTREND,
    HIGH_VOLATILITY,
    LOW_LIQUIDITY,
    RANGE,
    UPTREND,
    RegimeConfig,
    apply_regime_filter,
    detect_regime_series,
)


def _frame(close, volume=1000):
    close = pd.Series(close, dtype=float)
    return pd.DataFrame(
        {
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": volume,
        }
    )


def test_detect_regime_series_identifies_uptrend():
    frame = _frame(np.linspace(100, 150, 80))

    regimes = detect_regime_series(
        frame,
        RegimeConfig(short_window=5, long_window=20, adx_trend_threshold=5),
    )

    assert regimes.iloc[-1] == UPTREND


def test_detect_regime_series_identifies_range_when_trend_gap_is_small():
    frame = _frame([100, 101, 99, 100, 101, 99, 100, 101] * 10)

    regimes = detect_regime_series(
        frame,
        RegimeConfig(short_window=5, long_window=20, min_trend_gap=0.03, adx_trend_threshold=100),
    )

    assert regimes.iloc[-1] == RANGE


def test_detect_regime_series_identifies_high_volatility_before_trend():
    frame = _frame([100, 115, 90, 120, 85, 125, 80, 130] * 10)

    regimes = detect_regime_series(
        frame,
        RegimeConfig(short_window=5, long_window=20, high_volatility_threshold=0.2),
    )

    assert regimes.iloc[-1] == HIGH_VOLATILITY


def test_detect_regime_series_identifies_low_liquidity():
    volume = [1000] * 75 + [100]
    frame = _frame(np.linspace(100, 150, 76), volume=volume)

    regimes = detect_regime_series(
        frame,
        RegimeConfig(short_window=5, long_window=20, min_relative_volume=0.2),
    )

    assert regimes.iloc[-1] == LOW_LIQUIDITY


def test_low_liquidity_takes_precedence_over_high_volatility():
    volume = [1000] * 75 + [50]
    frame = _frame([100, 115, 90, 120, 85, 125, 80, 130] * 9 + [100, 140, 75, 150], volume=volume)

    regimes = detect_regime_series(
        frame,
        RegimeConfig(
            short_window=5,
            long_window=20,
            high_volatility_threshold=0.2,
            min_relative_volume=0.2,
        ),
    )

    assert regimes.iloc[-1] == LOW_LIQUIDITY


def test_regime_filter_blocks_trend_strategy_buys_outside_uptrend():
    events = pd.Series([1, 1, -1, 1])
    regimes = pd.Series([UPTREND, RANGE, RANGE, DOWNTREND])

    filtered = apply_regime_filter(events, regimes, "MA_CROSSOVER")

    assert filtered.tolist() == [1, 0, -1, 0]


def test_regime_filter_allows_mean_reversion_only_in_range_or_uptrend():
    events = pd.Series([1, 1, 1, -1])
    regimes = pd.Series([RANGE, UPTREND, DOWNTREND, HIGH_VOLATILITY])

    filtered = apply_regime_filter(events, regimes, "RSI")

    assert filtered.tolist() == [1, 1, 0, -1]


def test_regime_filter_blocks_buys_in_untradeable_regimes():
    events = pd.Series([1, 1, -1])
    regimes = pd.Series([HIGH_VOLATILITY, LOW_LIQUIDITY, LOW_LIQUIDITY])

    filtered = apply_regime_filter(events, regimes, "MACD_RSI")

    assert filtered.tolist() == [0, 0, -1]


def test_regime_filter_allows_ensemble_buys_in_uptrend_or_range_only():
    events = pd.Series([1, 1, 1, -1])
    regimes = pd.Series([UPTREND, RANGE, DOWNTREND, HIGH_VOLATILITY])

    filtered = apply_regime_filter(events, regimes, "ENSEMBLE_VOTE")

    assert filtered.tolist() == [1, 1, 0, -1]
