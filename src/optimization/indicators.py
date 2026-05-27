from __future__ import annotations

import numpy as np
import pandas as pd


def build_ohlcv_features(
    df: pd.DataFrame,
    *,
    atr_window: int = 14,
    adx_window: int = 14,
    volatility_window: int = 20,
    volume_window: int = 20,
) -> pd.DataFrame:
    """Build OHLCV-derived features with close-only fallbacks."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "close",
                "high",
                "low",
                "volume",
                "true_range",
                "atr",
                "adx",
                "realized_volatility",
                "relative_volume",
            ]
        )

    if "Close" not in df.columns and "close" not in df.columns:
        return pd.DataFrame()

    close = _numeric_column(df, "Close", "close")
    high = _numeric_column(df, "High", "high", fallback=close)
    low = _numeric_column(df, "Low", "low", fallback=close)
    volume = _numeric_column(df, "Volume", "volume")
    if volume.isna().all() or (volume.fillna(0.0) == 0.0).all():
        volume = pd.Series(1.0, index=close.index)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1).fillna(0.0)
    atr = true_range.rolling(max(int(atr_window), 1), min_periods=1).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=close.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=close.index,
    )
    directional_window = max(int(adx_window), 1)
    atr_for_di = true_range.rolling(directional_window, min_periods=1).mean().replace(0.0, np.nan)
    plus_di = 100.0 * plus_dm.rolling(directional_window, min_periods=1).mean() / atr_for_di
    minus_di = 100.0 * minus_dm.rolling(directional_window, min_periods=1).mean() / atr_for_di
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.rolling(directional_window, min_periods=1).mean().fillna(0.0).clip(0.0, 100.0)

    returns = close.pct_change().fillna(0.0)
    realized_volatility = (
        returns.rolling(max(int(volatility_window), 1), min_periods=1).std().fillna(0.0)
        * np.sqrt(252)
    )
    volume_average = volume.rolling(max(int(volume_window), 1), min_periods=1).mean()
    relative_volume = (volume / volume_average.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
    relative_volume = relative_volume.fillna(1.0)

    return pd.DataFrame(
        {
            "close": close.astype(float),
            "high": high.astype(float),
            "low": low.astype(float),
            "volume": volume.astype(float),
            "true_range": true_range.astype(float),
            "atr": atr.astype(float),
            "adx": adx.astype(float),
            "realized_volatility": realized_volatility.astype(float),
            "relative_volume": relative_volume.astype(float),
        },
        index=close.index,
    )


def _numeric_column(
    df: pd.DataFrame,
    primary: str,
    secondary: str,
    *,
    fallback: pd.Series | None = None,
) -> pd.Series:
    if primary in df.columns:
        series = df[primary]
    elif secondary in df.columns:
        series = df[secondary]
    elif fallback is not None:
        return fallback.astype(float)
    else:
        return pd.Series(0.0, index=df.index)

    numeric = pd.to_numeric(series, errors="coerce")
    if fallback is not None:
        numeric = numeric.fillna(fallback)
    return numeric.astype(float)
