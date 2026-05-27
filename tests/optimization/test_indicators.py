import numpy as np
import pandas as pd

from src.optimization.indicators import build_ohlcv_features


def test_build_ohlcv_features_calculates_atr_adx_volatility_and_relative_volume():
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    frame = pd.DataFrame(
        {
            "Open": np.linspace(99, 119, 40),
            "High": np.linspace(101, 123, 40),
            "Low": np.linspace(98, 117, 40),
            "Close": np.linspace(100, 120, 40),
            "Volume": np.linspace(1000, 2000, 40),
        },
        index=dates,
    )

    features = build_ohlcv_features(frame, atr_window=5, adx_window=5, volatility_window=5, volume_window=5)

    expected_columns = {
        "close",
        "high",
        "low",
        "volume",
        "true_range",
        "atr",
        "adx",
        "realized_volatility",
        "relative_volume",
    }
    assert expected_columns.issubset(features.columns)
    assert features["atr"].iloc[-1] > 0
    assert 0 <= features["adx"].iloc[-1] <= 100
    assert features["realized_volatility"].iloc[-1] >= 0
    assert features["relative_volume"].iloc[-1] > 0


def test_build_ohlcv_features_falls_back_to_close_only_data():
    frame = pd.DataFrame({"Close": [100, 101, 99, 102, 103]})

    features = build_ohlcv_features(frame, atr_window=3, adx_window=3, volatility_window=3, volume_window=3)

    assert features["high"].tolist() == frame["Close"].astype(float).tolist()
    assert features["low"].tolist() == frame["Close"].astype(float).tolist()
    assert features["relative_volume"].tolist() == [1.0] * len(frame)
    assert features["atr"].notna().all()


def test_build_ohlcv_features_returns_empty_when_close_is_missing():
    frame = pd.DataFrame({"Volume": [1000, 1200, 900]})

    features = build_ohlcv_features(frame)

    assert features.empty


def test_adx_window_is_independent_from_atr_window():
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    close = pd.Series(
        [100, 103, 101, 105, 102, 106, 104, 108, 103, 107] * 6,
        index=dates,
        dtype=float,
    )
    frame = pd.DataFrame(
        {
            "High": close + [1, 2, 1, 3, 1, 2, 1, 3, 1, 2] * 6,
            "Low": close - [1, 1, 2, 1, 3, 1, 2, 1, 3, 1] * 6,
            "Close": close,
            "Volume": 1000,
        },
        index=dates,
    )

    short_adx = build_ohlcv_features(frame, atr_window=5, adx_window=3)["adx"]
    long_adx = build_ohlcv_features(frame, atr_window=5, adx_window=20)["adx"]

    assert not short_adx.equals(long_adx)
