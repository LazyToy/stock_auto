"""
streak_indicators — 52-week high/low flag, N-day directional streak, ATR14.
"""
from __future__ import annotations

import math

import pandas as pd

LOOKBACK_52W = 252
ATR_PERIOD = 14


def _closes(obj: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(obj, pd.Series):
        return obj.dropna()
    if "Close" in obj.columns:
        close_col = obj["Close"]
        if isinstance(close_col, pd.Series):
            return close_col.dropna()
    raise KeyError("streak_indicators: DataFrame is missing a 'Close' column")


def is_52w_high(closes: pd.Series | pd.DataFrame, lookback: int = LOOKBACK_52W) -> bool:
    s = _closes(closes)
    if len(s) == 0:
        return False
    window = s.iloc[-lookback:]
    return bool(float(window.iloc[-1]) >= float(window.max()))


def is_52w_low(closes: pd.Series | pd.DataFrame, lookback: int = LOOKBACK_52W) -> bool:
    s = _closes(closes)
    if len(s) == 0:
        return False
    window = s.iloc[-lookback:]
    return bool(float(window.iloc[-1]) <= float(window.min()))


def current_streak(closes: pd.Series | pd.DataFrame) -> int:
    s = _closes(closes)
    n = len(s)
    if n < 2:
        return 0

    values = s.to_numpy()
    last = float(values[-1])
    prev = float(values[-2])
    if last == prev:
        return 0
    direction = 1 if last > prev else -1

    streak = 1
    for i in range(n - 2, 0, -1):
        a = float(values[i])
        b = float(values[i - 1])
        if a == b:
            break
        step = 1 if a > b else -1
        if step != direction:
            break
        streak += 1
    return streak * direction


def atr14(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    if df is None or len(df) == 0:
        return 0.0
    needed = {"High", "Low", "Close"}
    if not needed.issubset(df.columns):
        raise KeyError(f"streak_indicators: DataFrame missing columns {needed - set(df.columns)}")

    tail = df.iloc[-(period + 1):] if len(df) > period + 1 else df
    high = tail["High"].to_numpy(dtype=float)
    low = tail["Low"].to_numpy(dtype=float)
    close = tail["Close"].to_numpy(dtype=float)

    trs: list[float] = []
    for i in range(len(tail)):
        hl = high[i] - low[i]
        if i == 0:
            trs.append(hl)
            continue
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        trs.append(max(hl, hc, lc))

    if not trs:
        return 0.0
    window = trs[-period:] if len(trs) > period else trs
    return float(sum(window) / len(window))


def compute_indicators(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {
            "is_52w_high": False,
            "is_52w_low": False,
            "streak_days": 0,
            "atr14": 0.0,
            "atr14_pct": 0.0,
        }

    last_close = float(df["Close"].iloc[-1]) if "Close" in df.columns else 0.0
    atr_val = atr14(df)
    pct = (atr_val / last_close * 100.0) if last_close else 0.0
    if not math.isfinite(pct):
        pct = 0.0

    return {
        "is_52w_high": is_52w_high(df),
        "is_52w_low": is_52w_low(df),
        "streak_days": int(current_streak(df)),
        "atr14": atr_val,
        "atr14_pct": round(pct, 4),
    }
