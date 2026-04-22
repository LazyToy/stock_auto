"""
이슈 #7: 조기신호 판정 로직.

순수 함수만 포함 — 네트워크/시트 I/O 없음.
"""
from __future__ import annotations

from src.crawling._env_overrides import read_env_float, read_env_int

_RVOL_MIN = read_env_float("CRAWL_EARLY_SIGNAL_RVOL_MIN", 3.0)
_CHANGE_MIN = read_env_float("CRAWL_EARLY_SIGNAL_CHANGE_MIN", 3.0)
_CHANGE_MAX = read_env_float("CRAWL_EARLY_SIGNAL_CHANGE_MAX", 10.0)
_STREAK_MIN = read_env_int("CRAWL_EARLY_SIGNAL_STREAK_MIN", 3)
_RATIO_52W_MIN = read_env_float("CRAWL_EARLY_SIGNAL_RATIO_52W_MIN", 0.95)

EARLY_SIGNAL_HEADERS: list[str] = [
    "날짜",
    "종목코드",
    "종목명",
    "등락률(%)",
    "RVOL",
    "연속봉",
    "52주고가비율",
    "합산거래대금(억)",
    "5일후수익률(%)",
]


def has_early_signal_momentum(change: float, rvol: float | None) -> bool:
    if rvol is None:
        return False
    if rvol < _RVOL_MIN:
        return False
    return _CHANGE_MIN <= change <= _CHANGE_MAX


def is_early_signal(
    change: float,
    rvol: float,
    streak: int,
    close_ratio_52w: float,
) -> bool:
    if not has_early_signal_momentum(change, rvol):
        return False
    streak_ok = streak >= _STREAK_MIN
    near_52w_high = close_ratio_52w >= _RATIO_52W_MIN
    return streak_ok or near_52w_high


def build_early_signal_row(
    date: str,
    ticker: str,
    name: str,
    change: float,
    rvol: float,
    streak: int,
    close_ratio_52w: float,
    amount: float,
) -> list:
    return [
        date,
        ticker,
        name,
        round(float(change), 2),
        round(float(rvol), 2),
        int(streak),
        round(float(close_ratio_52w), 4),
        round(float(amount) / 1e8, 2),
        "",
    ]
