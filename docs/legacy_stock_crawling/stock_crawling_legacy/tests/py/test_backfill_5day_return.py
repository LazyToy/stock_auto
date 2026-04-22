"""
이슈 #7 AC-4: 5영업일 뒤 자동 백필 단위 테스트.

backfill_early_signal_returns(...)가
  - 5영업일 지난 행만 업데이트하고
  - 이미 값이 있는 행은 스킵하고
  - OHLCV 조회 실패 행은 스킵한다
는 계약을 검증.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ---------------------------------------------------------------------------
# Fake MarketFlowSheet — _ensure_worksheet + update_5day_return 만 흉내냄
# ---------------------------------------------------------------------------

class _FakeWorksheet:
    def __init__(self, rows: list[list]) -> None:
        self._rows = [list(r) for r in rows]
        self.updates: list[tuple[int, int, object]] = []

    def get_all_values(self) -> list[list]:
        return [list(r) for r in self._rows]

    def update_cell(self, row: int, col: int, value) -> None:
        self.updates.append((row, col, value))
        while len(self._rows) < row:
            self._rows.append([""] * col)
        while len(self._rows[row - 1]) < col:
            self._rows[row - 1].append("")
        self._rows[row - 1][col - 1] = value


class _FakeMarketFlowSheet:
    """조기신호_관찰 탭을 흉내내는 최소 스텁."""

    def __init__(self, rows: list[list]) -> None:
        from daily_trend_writer import EARLY_SIGNAL_HEADERS
        values = [list(EARLY_SIGNAL_HEADERS)] + [list(r) for r in rows]
        self._ws = _FakeWorksheet(values)
        self._update_calls: list[tuple[str, str, float]] = []

    def _ensure_worksheet(self, title: str, headers: list[str]):
        return self._ws

    def update_5day_return(self, date: str, ticker: str, return_pct: float) -> bool:
        self._update_calls.append((date, ticker, round(float(return_pct), 2)))
        values = self._ws.get_all_values()
        for i, row in enumerate(values[1:], start=2):
            if len(row) >= 2 and row[0] == date and row[1] == ticker:
                self._ws.update_cell(i, len(row), round(float(return_pct), 2))
                return True
        return False


def _row(date: str, ticker: str, five_day_ret: str = "") -> list:
    """EARLY_SIGNAL_HEADERS 스키마에 맞는 fake row."""
    return [date, ticker, "name", 5.0, 3.0, 3, 0.95, 100.0, five_day_ret]


# ---------------------------------------------------------------------------
# is_backfill_ready — 순수 함수
# ---------------------------------------------------------------------------

def test_is_backfill_ready_true_when_5_bdays_elapsed():
    """신호 2026-04-10(금) → today 2026-04-17(금) 사이 영업일 5일 경과."""
    from backfill_5day_return import is_backfill_ready
    assert is_backfill_ready("2026-04-10", _dt.date(2026, 4, 17), 5) is True


def test_is_backfill_ready_false_when_too_soon():
    """신호 2026-04-15(수) → today 2026-04-17(금) 사이 영업일 2일뿐."""
    from backfill_5day_return import is_backfill_ready
    assert is_backfill_ready("2026-04-15", _dt.date(2026, 4, 17), 5) is False


def test_is_backfill_ready_false_when_signal_in_future():
    from backfill_5day_return import is_backfill_ready
    assert is_backfill_ready("2027-01-01", _dt.date(2026, 4, 17), 5) is False


def test_is_backfill_ready_false_on_invalid_date():
    from backfill_5day_return import is_backfill_ready
    assert is_backfill_ready("not-a-date", _dt.date(2026, 4, 17), 5) is False


# ---------------------------------------------------------------------------
# compute_5day_return — 순수 함수
# ---------------------------------------------------------------------------

def test_compute_5day_return_positive():
    from backfill_5day_return import compute_5day_return
    assert abs(compute_5day_return(100.0, 110.0) - 10.0) < 1e-6


def test_compute_5day_return_negative():
    from backfill_5day_return import compute_5day_return
    assert abs(compute_5day_return(100.0, 95.0) - (-5.0)) < 1e-6


def test_compute_5day_return_zero_base_returns_zero():
    from backfill_5day_return import compute_5day_return
    assert compute_5day_return(0.0, 100.0) == 0.0


# ---------------------------------------------------------------------------
# backfill_early_signal_returns — 메인 로직
# ---------------------------------------------------------------------------

def test_backfill_updates_eligible_row():
    """5영업일 지났고 5일후수익률이 비어있으면 업데이트."""
    from backfill_5day_return import backfill_early_signal_returns

    sheet = _FakeMarketFlowSheet([
        _row("2026-04-10", "005930", five_day_ret=""),
    ])

    # close_lookup: (ticker, date_str) → close
    closes = {
        ("005930", "2026-04-10"): 100.0,
        ("005930", "2026-04-17"): 110.0,
    }

    def lookup(ticker: str, date_str: str):
        return closes.get((ticker, date_str))

    updated = backfill_early_signal_returns(
        sheet,
        today=_dt.date(2026, 4, 17),
        close_lookup=lookup,
        lookback=5,
    )
    assert updated == 1
    assert sheet._update_calls == [("2026-04-10", "005930", 10.0)]


def test_backfill_skips_filled_row():
    """이미 값이 있는 행은 건너뛴다."""
    from backfill_5day_return import backfill_early_signal_returns

    sheet = _FakeMarketFlowSheet([
        _row("2026-04-10", "005930", five_day_ret="7.50"),
    ])

    def lookup(_t, _d):
        raise AssertionError("lookup should not be called for filled row")

    updated = backfill_early_signal_returns(
        sheet,
        today=_dt.date(2026, 4, 17),
        close_lookup=lookup,
        lookback=5,
    )
    assert updated == 0
    assert sheet._update_calls == []


def test_backfill_skips_too_recent_row():
    """5영업일이 아직 안 지난 행은 스킵."""
    from backfill_5day_return import backfill_early_signal_returns

    sheet = _FakeMarketFlowSheet([
        _row("2026-04-15", "005930", five_day_ret=""),
    ])

    def lookup(_t, _d):
        raise AssertionError("lookup should not be called for too-recent row")

    updated = backfill_early_signal_returns(
        sheet,
        today=_dt.date(2026, 4, 17),
        close_lookup=lookup,
        lookback=5,
    )
    assert updated == 0
    assert sheet._update_calls == []


def test_backfill_skips_row_when_lookup_returns_none():
    """close_lookup 이 None 반환 시 해당 행 스킵."""
    from backfill_5day_return import backfill_early_signal_returns

    sheet = _FakeMarketFlowSheet([
        _row("2026-04-10", "009999", five_day_ret=""),
    ])

    def lookup(_t, _d):
        return None

    updated = backfill_early_signal_returns(
        sheet,
        today=_dt.date(2026, 4, 17),
        close_lookup=lookup,
        lookback=5,
    )
    assert updated == 0


def test_backfill_handles_multiple_rows():
    """여러 행 중 eligible 만 업데이트."""
    from backfill_5day_return import backfill_early_signal_returns

    sheet = _FakeMarketFlowSheet([
        _row("2026-04-10", "005930", five_day_ret=""),   # eligible
        _row("2026-04-10", "000660", five_day_ret="3.00"),  # already filled
        _row("2026-04-15", "373220", five_day_ret=""),   # too recent
    ])

    closes = {
        ("005930", "2026-04-10"): 50_000,
        ("005930", "2026-04-17"): 52_500,
    }

    def lookup(ticker: str, date_str: str):
        return closes.get((ticker, date_str))

    updated = backfill_early_signal_returns(
        sheet,
        today=_dt.date(2026, 4, 17),
        close_lookup=lookup,
        lookback=5,
    )
    assert updated == 1
    assert sheet._update_calls == [("2026-04-10", "005930", 5.0)]


if __name__ == "__main__":
    test_is_backfill_ready_true_when_5_bdays_elapsed()
    test_is_backfill_ready_false_when_too_soon()
    test_is_backfill_ready_false_when_signal_in_future()
    test_is_backfill_ready_false_on_invalid_date()
    test_compute_5day_return_positive()
    test_compute_5day_return_negative()
    test_compute_5day_return_zero_base_returns_zero()
    test_backfill_updates_eligible_row()
    test_backfill_skips_filled_row()
    test_backfill_skips_too_recent_row()
    test_backfill_skips_row_when_lookup_returns_none()
    test_backfill_handles_multiple_rows()
    print("[PASS] test_backfill_5day_return 전체 통과")
