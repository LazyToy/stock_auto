"""
TDD test: streak_indicators — 52-week high/low, N-day streak, ATR14.

Hermetic — builds tiny synthetic pandas DataFrames with hand-verifiable
values. No network, no FinanceDataReader.

Run
---
    ./stock_crawling/Scripts/python.exe test_streak_indicators.py
"""
from __future__ import annotations

import math
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 streak_indicators 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd

from streak_indicators import (
    atr14,
    compute_indicators,
    current_streak,
    is_52w_high,
    is_52w_low,
)

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" - {detail}" if detail else ""))


def close_only(values: list[float]) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, name="Close")


def ohlc(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close"])


# ---------------------------------------------------------------------------
# 1. is_52w_high
# ---------------------------------------------------------------------------

rising = close_only([100.0 + i for i in range(260)])
check("is_52w_high on rising series -> True",
      is_52w_high(rising) is True)

plateau_then_dip = close_only([100.0 + i for i in range(260)] + [259.0])
check("is_52w_high when last is below window max -> False",
      is_52w_high(plateau_then_dip) is False)

exact_tie = close_only([200.0] * 300)
check("is_52w_high on a flat series -> True (last equals max)",
      is_52w_high(exact_tie) is True)

short_series = close_only([10.0, 11.0, 12.0])
check("is_52w_high on short series still evaluates last vs max of available",
      is_52w_high(short_series) is True)

# Window-scoped: a super-high value outside the 252-day window should
# NOT prevent a 52-week high today.
spike_outside = close_only([999.0] + [50.0 + i for i in range(260)])
check("is_52w_high ignores data older than the window",
      is_52w_high(spike_outside, lookback=252) is True)

# ---------------------------------------------------------------------------
# 2. is_52w_low
# ---------------------------------------------------------------------------

falling = close_only([500.0 - i for i in range(260)])
check("is_52w_low on falling series -> True",
      is_52w_low(falling) is True)

low_middle = close_only([50.0 + i for i in range(260)])
check("is_52w_low when last is above window min -> False",
      is_52w_low(low_middle) is False)

# ---------------------------------------------------------------------------
# 3. current_streak
# ---------------------------------------------------------------------------

# 3 up days in a row — compare pairs (d1>d0, d2>d1, d3>d2)
up3 = close_only([100.0, 101.0, 102.0, 103.0])
check("current_streak 3 up days -> +3",
      current_streak(up3) == 3, f"got {current_streak(up3)}")

down2 = close_only([100.0, 99.0, 98.0])
check("current_streak 2 down days -> -2",
      current_streak(down2) == -2, f"got {current_streak(down2)}")

mixed = close_only([100.0, 99.0, 100.0, 101.0, 102.0])
check("current_streak resets on direction change - last 3 up -> +3",
      current_streak(mixed) == 3, f"got {current_streak(mixed)}")

flat_end = close_only([100.0, 101.0, 101.0])
check("flat day breaks streak -> 0",
      current_streak(flat_end) == 0, f"got {current_streak(flat_end)}")

single = close_only([100.0])
check("single row -> streak 0", current_streak(single) == 0)

# ---------------------------------------------------------------------------
# 4. atr14 — hand-computed on a 15-row synthetic OHLC
# ---------------------------------------------------------------------------

# Build 15 rows where High-Low is always exactly 2 and prev-close gap is 0:
# that makes TR = 2 for every row except the first (which has no prev close)
# and the simple 14-period ATR should be exactly 2.
rows = [(100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i) for i in range(15)]
flat_atr_df = ohlc(rows)
val = atr14(flat_atr_df)
check("atr14 on constant-range OHLC -> 2.0",
      math.isclose(val, 2.0, rel_tol=1e-9, abs_tol=1e-9),
      f"got {val}")

# When the series is shorter than 15 rows, ATR14 is still defined over the
# available TR values — but we require NaN fallback to be *not* NaN.
short_ohlc = ohlc([(10.0, 11.0, 9.0, 10.0), (11.0, 12.0, 10.0, 11.0)])
short_val = atr14(short_ohlc)
check("atr14 on short series returns a finite float",
      isinstance(short_val, float) and math.isfinite(short_val),
      f"got {short_val}")

# ---------------------------------------------------------------------------
# 5. compute_indicators — end-to-end dict
# ---------------------------------------------------------------------------

# 260-row rising OHLC — should hit 52w high, 259-day up streak, stable ATR
rows260 = [
    (100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i)
    for i in range(260)
]
big_df = ohlc(rows260)
ind = compute_indicators(big_df)

check("compute_indicators returns a dict",
      isinstance(ind, dict))
check("compute_indicators contains is_52w_high",
      ind.get("is_52w_high") is True)
check("compute_indicators contains is_52w_low",
      ind.get("is_52w_low") is False)
check("compute_indicators contains positive streak",
      isinstance(ind.get("streak_days"), int) and ind["streak_days"] > 0,
      f"got streak={ind.get('streak_days')}")
check("compute_indicators contains numeric atr14",
      isinstance(ind.get("atr14"), float) and math.isfinite(ind["atr14"]),
      f"got atr14={ind.get('atr14')}")
check("compute_indicators contains atr14_pct",
      isinstance(ind.get("atr14_pct"), float) and math.isfinite(ind["atr14_pct"]),
      f"got atr14_pct={ind.get('atr14_pct')}")
check("atr14 ~= 2.0 on constant-range rising OHLC",
      math.isclose(ind["atr14"], 2.0, rel_tol=1e-9, abs_tol=1e-9))

# Empty DataFrame must not explode — returns a well-formed dict with
# is_52w_high=False, streak_days=0, atr14=nan-or-0.0 (finite requirement
# relaxed for the empty case).
empty = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
ind_empty = compute_indicators(empty)
check("compute_indicators on empty frame returns dict",
      isinstance(ind_empty, dict))
check("compute_indicators on empty frame has is_52w_high=False",
      ind_empty.get("is_52w_high") is False)
check("compute_indicators on empty frame has streak_days=0",
      ind_empty.get("streak_days") == 0)

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

passed = sum(1 for r in results if r)
total = len(results)
print()
print("=" * 60)
print(f"  RESULT: {passed}/{total} checks passed")
print("=" * 60)

sys.exit(0 if passed == total else 1)
