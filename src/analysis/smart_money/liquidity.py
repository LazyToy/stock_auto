"""Liquidity sweep 탐지."""

from __future__ import annotations

import logging
from typing import cast

import pandas as pd

from src.analysis.smart_money.models import (
    LiquiditySweep,
    LiquiditySweepDirection,
    SwingPoint,
    SwingType,
)

logger = logging.getLogger(__name__)

DEFAULT_SWEEP_TOLERANCE_PCT: float = 0.001
_REQUIRED_COLUMNS: tuple[str, ...] = ("high", "low", "close")


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    tolerance_pct: float = DEFAULT_SWEEP_TOLERANCE_PCT,
) -> list[LiquiditySweep]:
    """확정 swing level을 찌른 뒤 되돌린 liquidity sweep을 탐지한다."""
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")
    if swings is None:
        raise ValueError("swings가 None입니다. 빈 리스트([])를 전달하세요.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("df의 인덱스가 DatetimeIndex가 아닙니다.")
    if tolerance_pct < 0:
        raise ValueError(f"tolerance_pct는 0 이상이어야 합니다. 현재 값: {tolerance_pct}")
    if len(df) == 0 or not swings:
        return []

    missing = [column for column in _REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        logger.warning("필수 컬럼 누락으로 liquidity sweep을 탐지할 수 없습니다: %s", missing)
        return []

    ordered_swings = sorted(swings, key=lambda item: (item.bar_index, item.timestamp))
    sweeps: list[LiquiditySweep] = []
    used: set[tuple[SwingType, int]] = set()
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for bar_index in range(len(df)):
        past_swings = [swing for swing in ordered_swings if swing.bar_index < bar_index]
        if not past_swings:
            continue

        high_swing = _latest_unused_swing(past_swings, SwingType.HIGH, used)
        if high_swing is not None and _is_bearish_high_sweep(
            high=float(highs[bar_index]),
            close=float(closes[bar_index]),
            level=high_swing.price,
            tolerance_pct=tolerance_pct,
        ):
            sweeps.append(
                LiquiditySweep(
                    direction=LiquiditySweepDirection.BEARISH,
                    swept_level=float(high_swing.price),
                    timestamp=cast(pd.Timestamp, df.index[bar_index]).to_pydatetime(),
                    bar_index=bar_index,
                    swept_swing_bar_index=high_swing.bar_index,
                )
            )
            used.add((high_swing.swing_type, high_swing.bar_index))

        low_swing = _latest_unused_swing(past_swings, SwingType.LOW, used)
        if low_swing is not None and _is_bullish_low_sweep(
            low=float(lows[bar_index]),
            close=float(closes[bar_index]),
            level=low_swing.price,
            tolerance_pct=tolerance_pct,
        ):
            sweeps.append(
                LiquiditySweep(
                    direction=LiquiditySweepDirection.BULLISH,
                    swept_level=float(low_swing.price),
                    timestamp=cast(pd.Timestamp, df.index[bar_index]).to_pydatetime(),
                    bar_index=bar_index,
                    swept_swing_bar_index=low_swing.bar_index,
                )
            )
            used.add((low_swing.swing_type, low_swing.bar_index))

    sweeps.sort(key=lambda item: (item.bar_index, item.timestamp, item.direction.value))
    return sweeps


def _latest_unused_swing(
    swings: list[SwingPoint],
    swing_type: SwingType,
    used: set[tuple[SwingType, int]],
) -> SwingPoint | None:
    candidates = [
        swing
        for swing in swings
        if swing.swing_type == swing_type and (swing.swing_type, swing.bar_index) not in used
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.bar_index, item.timestamp))


def _is_bearish_high_sweep(
    *,
    high: float,
    close: float,
    level: float,
    tolerance_pct: float,
) -> bool:
    threshold = level * (1.0 + tolerance_pct)
    return high > threshold and close < level


def _is_bullish_low_sweep(
    *,
    low: float,
    close: float,
    level: float,
    tolerance_pct: float,
) -> bool:
    threshold = level * (1.0 - tolerance_pct)
    return low < threshold and close > level
