"""
이슈 #7 AC-4: 조기신호_관찰 탭의 5일후수익률(%) 백필 잡.

설계 원칙
--------
* is_backfill_ready / compute_5day_return 은 **순수 함수** — 네트워크/시트 I/O 없음.
* backfill_early_signal_returns 는 sheet 와 close_lookup 을 injectable 로 받아
  테스트에서 Fake 로 교체 가능.
* main() 은 production 와이어링 — FDR DataReader 로 KR 종목 과거 종가 조회.

시장흐름_{YYYY} 스프레드시트의 조기신호_관찰 탭을 열어
5일후수익률(%)가 비어있고 신호일로부터 5영업일 이상 지난 행을 찾아
신호일 종가 및 T+5 영업일 종가로부터 수익률을 계산해 업데이트한다.

실행
----
    PYTHONIOENCODING=utf-8 ./stock_crawling/Scripts/python.exe backfill_5day_return.py
"""
from __future__ import annotations

import datetime as _dt
import sys
import traceback
from typing import Callable, cast

_DEFAULT_LOOKBACK = 5


def is_backfill_ready(
    signal_date: str,
    today: _dt.date,
    lookback: int = _DEFAULT_LOOKBACK,
) -> bool:
    """signal_date 로부터 today 까지 lookback 영업일 이상 경과했는지.

    * bdate_range 는 양끝 포함이므로 len - 1 이 "간격"이 된다.
    * 유효하지 않은 날짜/미래 날짜는 False 반환.
    """
    try:
        sd = _dt.date.fromisoformat(signal_date)
    except (ValueError, TypeError):
        return False
    if sd > today:
        return False
    import pandas as pd
    try:
        bd = pd.bdate_range(sd, today)
    except Exception:
        return False
    return (len(bd) - 1) >= lookback


def compute_5day_return(signal_close: float, plus5_close: float) -> float:
    """(plus5_close / signal_close - 1) * 100. 베이스 0 이하면 0.0 반환."""
    if signal_close is None or plus5_close is None:
        return 0.0
    if signal_close <= 0:
        return 0.0
    return (float(plus5_close) / float(signal_close) - 1.0) * 100.0


def _plus_bdays(signal_date: str, n: int) -> str | None:
    """signal_date 로부터 n 영업일 뒤 날짜 ('YYYY-MM-DD'). 실패 시 None."""
    try:
        sd = _dt.date.fromisoformat(signal_date)
    except (ValueError, TypeError):
        return None
    import pandas as pd
    try:
        bd = pd.bdate_range(sd, sd + _dt.timedelta(days=n * 2 + 5))
    except Exception:
        return None
    if len(bd) <= n:
        return None
    dates_list = list(bd)
    target = dates_list[n]
    return cast(str, target.strftime("%Y-%m-%d"))


def backfill_early_signal_returns(
    mf_sheet,
    today: _dt.date,
    close_lookup: Callable[[str, str], float | None],
    lookback: int = _DEFAULT_LOOKBACK,
) -> int:
    """조기신호_관찰 탭의 5일후수익률(%) 컬럼을 백필.

    Parameters
    ----------
    mf_sheet : MarketFlowSheet (or fake) — ``_ensure_worksheet`` 와
               ``update_5day_return`` 를 제공해야 한다.
    today    : 오늘 날짜 (``datetime.date``).
    close_lookup : ``(ticker, 'YYYY-MM-DD') → close|None`` 콜러블.
    lookback : 백필 기준 영업일 수 (기본 5).

    Returns
    -------
    int — 실제로 업데이트된 행 수.
    """
    from src.crawling.daily_trend_writer import EARLY_SIGNAL_TAB, EARLY_SIGNAL_HEADERS

    ws = mf_sheet._ensure_worksheet(EARLY_SIGNAL_TAB, EARLY_SIGNAL_HEADERS)
    values = ws.get_all_values()

    updated = 0
    for row in values[1:]:
        if len(row) < 2 or not row[0]:
            continue
        signal_date = str(row[0]).strip()
        ticker = str(row[1]).strip()
        if not ticker:
            continue

        # 이미 5일후수익률이 채워진 행은 스킵
        already_filled = len(row) >= len(EARLY_SIGNAL_HEADERS) and str(row[-1]).strip() != ""
        if already_filled:
            continue

        if not is_backfill_ready(signal_date, today, lookback):
            continue

        sd_close = close_lookup(ticker, signal_date)
        if sd_close is None:
            continue

        plus_date = _plus_bdays(signal_date, lookback)
        if plus_date is None:
            continue
        p5_close = close_lookup(ticker, plus_date)
        if p5_close is None:
            continue

        ret = compute_5day_return(float(sd_close), float(p5_close))
        if mf_sheet.update_5day_return(signal_date, ticker, ret):
            updated += 1

    return updated


# ---------------------------------------------------------------------------
# Production wiring — not unit-tested
# ---------------------------------------------------------------------------

def _production_close_lookup_factory() -> Callable[[str, str], float | None]:
    """FDR DataReader 로 KR 종목 종가 캐싱 조회."""
    import pandas as pd
    import importlib
    fdr = importlib.import_module("FinanceDataReader")

    import pandas as pd
    cache: dict[str, pd.DataFrame] = {}

    def _lookup(ticker: str, date_str: str) -> float | None:
        try:
            df = cache.get(ticker)
            if df is None:
                df = fdr.DataReader(ticker, start=None)
                if df is None or len(df) == 0:
                    return None
                cache[ticker] = df
            target = pd.Timestamp(date_str)
            # index 가 DatetimeIndex 라고 가정. 정확 매치 없으면 직전 영업일 종가 반환.
            if hasattr(df, "index") and len(df) > 0:
                idx = df.index
                if target in idx:
                    return float(df.loc[target]["Close"])
                # 가까운 과거 영업일 조회
                earlier = df.loc[df.index <= target]
                if len(earlier) > 0:
                    return float(earlier.iloc[-1]["Close"])
            return None
        except Exception:
            return None

    return _lookup


def main() -> int:
    try:
        from daily_trend_writer import MarketFlowSheet, make_sheet_client
    except Exception:
        print("[backfill] daily_trend_writer import 실패", file=sys.stderr)
        traceback.print_exc(limit=5)
        return 1

    today = _dt.date.today()
    year = today.year

    try:
        gc = make_sheet_client()
        mf_sheet = MarketFlowSheet(gc, year)
    except Exception:
        print("[backfill] gspread 클라이언트 생성 실패", file=sys.stderr)
        traceback.print_exc(limit=5)
        return 1

    close_lookup = _production_close_lookup_factory()

    try:
        updated = backfill_early_signal_returns(mf_sheet, today, close_lookup)
        print(f"[backfill] 5일후수익률 백필 완료 — {updated}행 업데이트")
        return 0
    except Exception:
        print("[backfill] 백필 실패:", file=sys.stderr)
        traceback.print_exc(limit=5)
        return 1


if __name__ == "__main__":
    sys.exit(main())
