from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def _make_df(rows: list[dict], start: str = "2024-01-02", freq: str = "1D") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=index)


def _candle(open_price: float, high: float, low: float, close: float) -> dict:
    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _swing(price: float, swing_type: str, bar_index: int):
    from src.analysis.smart_money.models import SwingPoint, SwingType

    return SwingPoint(
        timestamp=datetime(2024, 1, 2) + timedelta(days=bar_index),
        price=price,
        swing_type=SwingType.HIGH if swing_type == "HIGH" else SwingType.LOW,
        bar_index=bar_index,
    )


def test_high_sweep_that_closes_back_below_level_is_bearish_liquidity_sweep() -> None:
    """이전 swing high 위를 찌른 뒤 아래 종가면 bearish liquidity sweep이다."""
    from src.analysis.smart_money.liquidity import detect_liquidity_sweeps
    from src.analysis.smart_money.models import LiquiditySweepDirection

    df = _make_df(
        [
            _candle(100, 103, 99, 101),
            _candle(101, 105, 100, 104),
            _candle(104, 111, 103, 108),
            _candle(108, 112, 106, 109.5),
        ]
    )

    result = detect_liquidity_sweeps(df, [_swing(110.0, "HIGH", 2)])

    assert len(result) == 1
    assert result[0].direction == LiquiditySweepDirection.BEARISH
    assert result[0].swept_level == 110.0
    assert result[0].bar_index == 3


def test_low_sweep_that_closes_back_above_level_is_bullish_liquidity_sweep() -> None:
    """이전 swing low 아래를 찌른 뒤 위 종가면 bullish liquidity sweep이다."""
    from src.analysis.smart_money.liquidity import detect_liquidity_sweeps
    from src.analysis.smart_money.models import LiquiditySweepDirection

    df = _make_df(
        [
            _candle(110, 113, 109, 111),
            _candle(111, 112, 104, 105),
            _candle(105, 108, 99, 102),
            _candle(102, 106, 98, 100.5),
        ]
    )

    result = detect_liquidity_sweeps(df, [_swing(100.0, "LOW", 2)])

    assert len(result) == 1
    assert result[0].direction == LiquiditySweepDirection.BULLISH
    assert result[0].swept_level == 100.0
    assert result[0].bar_index == 3


def test_close_through_level_is_not_liquidity_sweep() -> None:
    """레벨을 찌른 뒤 되돌리지 않고 돌파 종가면 sweep으로 보지 않는다."""
    from src.analysis.smart_money.liquidity import detect_liquidity_sweeps

    df = _make_df(
        [
            _candle(100, 103, 99, 101),
            _candle(101, 105, 100, 104),
            _candle(104, 111, 103, 108),
            _candle(108, 112, 106, 111.5),
        ]
    )

    result = detect_liquidity_sweeps(df, [_swing(110.0, "HIGH", 2)])

    assert result == []
