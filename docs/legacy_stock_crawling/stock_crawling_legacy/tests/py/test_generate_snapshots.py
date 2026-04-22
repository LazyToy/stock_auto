"""
TDD test: generate_snapshots.run_snapshots — pipeline glue.

Hermetic. Both data sources and the sheet factory are injected.

Run
---
    PYTHONIOENCODING=utf-8 ./stock_crawling/Scripts/python.exe test_generate_snapshots.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd

from generate_snapshots import run_snapshots

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" - {detail}" if detail else ""))


def kr_fixture() -> dict:
    return dict(
        date="2026-04-13",
        total=2000, up=1200, down=800, flat=0,
        breadth=0.2, kospi_breadth=0.15, kosdaq_breadth=0.25,
        top20_volume_concentration=0.42,
        surge15_count=3, drop15_count=1, limit_up=0, limit_down=0,
        cap_weighted_change=0.8,
        top_gainers=pd.DataFrame([
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI",
             "ChagesRatio": 3.5, "Volume": 12_345_678, "Amount": 1e12},
        ]),
        ohlcv_rows=pd.DataFrame([
            {"Code": "005930", "Open": 70_000, "High": 72_000, "Low": 69_500, "Close": 71_000,
             "Volume": 12_345_678, "Amount": 1e12},
            {"Code": "000660", "Open": 150_000, "High": 151_000, "Low": 148_000, "Close": 149_000,
             "Volume": 3_210_000, "Amount": 5e11},
        ]),
        top_losers=pd.DataFrame([
            {"Code": "000660", "Name": "SK하이닉스", "Market": "KOSPI",
             "ChagesRatio": -2.1, "Amount": 5e11},
        ]),
        top_volume=pd.DataFrame([
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI",
             "ChagesRatio": 3.5, "Amount": 1e12},
        ]),
    )


def us_fixture() -> dict:
    return dict(
        date="2026-04-13",
        total=500, up=300, down=200, flat=0,
        breadth=0.2, cap_weighted_change=0.5,
        surge5_count=4, drop5_count=2,
        top_gainers=pd.DataFrame([
            {"Ticker": "NVDA", "Name": "NVIDIA", "Change": 4.2, "volume": 98_765_432,
             "Volume.Traded": 20e9, "Sector": "Electronic Technology"},
        ]),
        ohlcv_rows=pd.DataFrame([
            {"ticker": "NVDA", "close": 900, "high": 910, "low": 880, "volume": 98_765_432,
             "volume_value": 20e9},
            {"ticker": "AAPL", "close": 210, "high": 212, "low": 208, "volume": 45_000_000,
             "volume_value": 9e9},
        ]),
        top_losers=pd.DataFrame([
            {"Ticker": "TSLA", "Name": "Tesla", "Change": -3.1,
             "Volume.Traded": 10e9, "Sector": "Consumer Durables"},
        ]),
        top_volume=pd.DataFrame([
            {"Ticker": "NVDA", "Name": "NVIDIA", "Change": 4.2,
             "Volume.Traded": 20e9, "Sector": "Electronic Technology"},
        ]),
        sectors=pd.DataFrame([
            {"Sector": "Electronic Technology", "Change": 2.1, "Count": 50},
            {"Sector": "Consumer Durables", "Change": -1.2, "Count": 30},
        ]),
    )


class FakeSheet:
    def __init__(self, year: int) -> None:
        self.year = year
        self.kr_calls: list[dict] = []
        self.us_calls: list[dict] = []
        self.news_calls: list[tuple] = []

    def append_kr_snapshot(self, snap: dict) -> bool:
        self.kr_calls.append(snap)
        return True

    def append_us_snapshot(self, snap: dict) -> bool:
        self.us_calls.append(snap)
        return True

    def append_news_row(
        self,
        date: str,
        kr_keywords: list,
        us_keywords: list,
        narrative: str,
    ) -> bool:
        self.news_calls.append((date, kr_keywords, us_keywords, narrative))
        return True


# ---------------------------------------------------------------------------
# 1. Happy path — both sources succeed, both appended
# ---------------------------------------------------------------------------

sheets: list[FakeSheet] = []


def factory(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets.append(s)
    return s


rc = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory,
    clock=lambda: datetime(2026, 4, 13),
)
check("happy path returns 0", rc == 0)
check("factory called with year 2026", sheets and sheets[0].year == 2026)
check("KR snapshot appended once", sheets and len(sheets[0].kr_calls) == 1)
check("US snapshot appended once", sheets and len(sheets[0].us_calls) == 1)
check("KR snapshot payload matches fixture",
      sheets[0].kr_calls[0].get("total") == 2000)
check("US snapshot payload matches fixture",
      sheets[0].us_calls[0].get("total") == 500)


# ---------------------------------------------------------------------------
# 2. KR source raises → US still runs, rc=1
# ---------------------------------------------------------------------------

def kr_raises() -> dict:
    raise RuntimeError("fdr down")


sheets2: list[FakeSheet] = []


def factory2(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets2.append(s)
    return s


rc2 = run_snapshots(
    kr_source=kr_raises,
    us_source=us_fixture,
    sheet_factory=factory2,
    clock=lambda: datetime(2026, 4, 13),
)
check("KR failure → rc=1", rc2 == 1)
check("KR failure → US still appended", sheets2 and len(sheets2[0].us_calls) == 1)
check("KR failure → KR not appended", sheets2 and len(sheets2[0].kr_calls) == 0)


# ---------------------------------------------------------------------------
# 3. US source raises → KR still runs, rc=1
# ---------------------------------------------------------------------------

def us_raises() -> dict:
    raise RuntimeError("tv down")


sheets3: list[FakeSheet] = []


def factory3(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets3.append(s)
    return s


rc3 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_raises,
    sheet_factory=factory3,
    clock=lambda: datetime(2026, 4, 13),
)
check("US failure → rc=1", rc3 == 1)
check("US failure → KR still appended", sheets3 and len(sheets3[0].kr_calls) == 1)
check("US failure → US not appended", sheets3 and len(sheets3[0].us_calls) == 0)


# ---------------------------------------------------------------------------
# 4. Both fail → rc=1 but no crash
# ---------------------------------------------------------------------------

sheets4: list[FakeSheet] = []


def factory4(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets4.append(s)
    return s


rc4 = run_snapshots(
    kr_source=kr_raises,
    us_source=us_raises,
    sheet_factory=factory4,
    clock=lambda: datetime(2026, 4, 13),
)
check("both fail → rc=1", rc4 == 1)
check("both fail → no appends", sheets4 and
      len(sheets4[0].kr_calls) == 0 and len(sheets4[0].us_calls) == 0)


# ---------------------------------------------------------------------------
# 5. Sheet factory itself raises → rc=1, sources not even called
# ---------------------------------------------------------------------------

kr_called = [0]
us_called = [0]


def kr_track() -> dict:
    kr_called[0] += 1
    return kr_fixture()


def us_track() -> dict:
    us_called[0] += 1
    return us_fixture()


def factory_boom(year: int):
    raise RuntimeError("sheets unreachable")


rc5 = run_snapshots(
    kr_source=kr_track,
    us_source=us_track,
    sheet_factory=factory_boom,
    clock=lambda: datetime(2026, 4, 13),
)
check("sheet factory failure → rc=1", rc5 == 1)
check("sheet factory failure → sources never called",
      kr_called[0] == 0 and us_called[0] == 0)


# ---------------------------------------------------------------------------
# 6. Year is derived from clock
# ---------------------------------------------------------------------------

sheets6: list[FakeSheet] = []


def factory6(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets6.append(s)
    return s


run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory6,
    clock=lambda: datetime(2027, 1, 5),
)
check("year derived from clock = 2027",
      sheets6 and sheets6[0].year == 2027)


# ---------------------------------------------------------------------------
# 7. News source — happy path: receives both snaps, news row appended
# ---------------------------------------------------------------------------

received7: list[tuple] = []


def news_source_happy(kr_snap, us_snap):
    received7.append((kr_snap, us_snap))
    return (
        [("반도체", 5), ("실적", 3)],
        [("nvidia", 4), ("chip", 2)],
        "AI 요약 문장",
    )


sheets7: list[FakeSheet] = []


def factory7(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets7.append(s)
    return s


rc7 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory7,
    news_source=news_source_happy,
    clock=lambda: datetime(2026, 4, 13),
)
check("news happy: rc=0", rc7 == 0)
check("news happy: KR still appended",
      sheets7 and len(sheets7[0].kr_calls) == 1)
check("news happy: US still appended",
      sheets7 and len(sheets7[0].us_calls) == 1)
check("news happy: news row appended once",
      sheets7 and len(sheets7[0].news_calls) == 1)
check("news happy: news_source received both snaps",
      len(received7) == 1
      and received7[0][0] is not None
      and received7[0][0].get("total") == 2000
      and received7[0][1] is not None
      and received7[0][1].get("total") == 500)
check("news happy: news row date from snapshot",
      sheets7[0].news_calls[0][0] == "2026-04-13")
check("news happy: KR keywords forwarded verbatim",
      sheets7[0].news_calls[0][1] == [("반도체", 5), ("실적", 3)])
check("news happy: US keywords forwarded verbatim",
      sheets7[0].news_calls[0][2] == [("nvidia", 4), ("chip", 2)])
check("news happy: narrative forwarded",
      sheets7[0].news_calls[0][3] == "AI 요약 문장")


# ---------------------------------------------------------------------------
# 8. News source raises → rc=1, KR/US still appended, no crash
# ---------------------------------------------------------------------------

def news_raises(kr_snap, us_snap):
    raise RuntimeError("gemini down")


sheets8: list[FakeSheet] = []


def factory8(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets8.append(s)
    return s


rc8 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory8,
    news_source=news_raises,
    clock=lambda: datetime(2026, 4, 13),
)
check("news failure → rc=1", rc8 == 1)
check("news failure → KR still appended",
      sheets8 and len(sheets8[0].kr_calls) == 1)
check("news failure → US still appended",
      sheets8 and len(sheets8[0].us_calls) == 1)
check("news failure → no news row appended",
      sheets8 and len(sheets8[0].news_calls) == 0)


# ---------------------------------------------------------------------------
# 9. KR source fails but news_source still runs with kr_snap=None
# ---------------------------------------------------------------------------

received9: list[tuple] = []


def news_source_9(kr_snap, us_snap):
    received9.append((kr_snap, us_snap))
    return [], [("nvidia", 4)], "KR 데이터 없음"


sheets9: list[FakeSheet] = []


def factory9(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets9.append(s)
    return s


rc9 = run_snapshots(
    kr_source=kr_raises,
    us_source=us_fixture,
    sheet_factory=factory9,
    news_source=news_source_9,
    clock=lambda: datetime(2026, 4, 13),
)
check("news w/ KR fail: rc=1", rc9 == 1)
check("news w/ KR fail: news_source still called", len(received9) == 1)
check("news w/ KR fail: kr_snap=None, us_snap=dict",
      received9[0][0] is None
      and received9[0][1] is not None
      and received9[0][1].get("total") == 500)
check("news w/ KR fail: news row appended with us date",
      sheets9 and len(sheets9[0].news_calls) == 1
      and sheets9[0].news_calls[0][0] == "2026-04-13")


# ---------------------------------------------------------------------------
# 10. Sheet factory boom with news_source → news_source never called
# ---------------------------------------------------------------------------

news_call_count_10 = [0]


def news_source_10(kr_snap, us_snap):
    news_call_count_10[0] += 1
    return [], [], ""


def factory_boom_10(year: int):
    raise RuntimeError("sheets unreachable")


rc10 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory_boom_10,
    news_source=news_source_10,
    clock=lambda: datetime(2026, 4, 13),
)
check("news w/ factory boom: rc=1", rc10 == 1)
check("news w/ factory boom: news_source never called",
      news_call_count_10[0] == 0)


# ---------------------------------------------------------------------------
# 11. Backward compat: news_source omitted → existing behavior unchanged
# ---------------------------------------------------------------------------

sheets11: list[FakeSheet] = []


def factory11(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets11.append(s)
    return s


rc11 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory11,
    clock=lambda: datetime(2026, 4, 13),
)
check("no news_source → rc=0 (backward compat)", rc11 == 0)
check("no news_source → news_calls empty",
      sheets11 and len(sheets11[0].news_calls) == 0)


# ---------------------------------------------------------------------------
# 12. ohlcv_sink — 양쪽 스냅샷 성공 시 sink 호출, date_str 일치
# ---------------------------------------------------------------------------

sink_calls12: list[tuple] = []


def ohlcv_sink_capture(kr_snap, us_snap, date_str):
    sink_calls12.append((kr_snap, us_snap, date_str))


sheets12: list[FakeSheet] = []


def factory12(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets12.append(s)
    return s


rc12 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory12,
    ohlcv_sink=ohlcv_sink_capture,
    clock=lambda: datetime(2026, 4, 17),
)
check("ohlcv_sink: rc=0", rc12 == 0)
check("ohlcv_sink: called exactly once", len(sink_calls12) == 1)
check("ohlcv_sink: date_str is YYYY-MM-DD",
      sink_calls12 and sink_calls12[0][2] == "2026-04-17")
check("ohlcv_sink: kr_snap passed non-None",
      sink_calls12 and sink_calls12[0][0] is not None)


# ---------------------------------------------------------------------------
# 13. ohlcv_sink raises → rc=1, pipeline does not crash
# ---------------------------------------------------------------------------

def ohlcv_sink_boom(_kr, _us, _date):
    raise RuntimeError("disk full")


sheets13: list[FakeSheet] = []


def factory13(year: int) -> FakeSheet:
    s = FakeSheet(year)
    sheets13.append(s)
    return s


rc13 = run_snapshots(
    kr_source=kr_fixture,
    us_source=us_fixture,
    sheet_factory=factory13,
    ohlcv_sink=ohlcv_sink_boom,
    clock=lambda: datetime(2026, 4, 17),
)
check("ohlcv_sink raises → rc=1", rc13 == 1)
check("ohlcv_sink raises → KR/US still appended",
      sheets13 and len(sheets13[0].kr_calls) == 1 and len(sheets13[0].us_calls) == 1)


# ---------------------------------------------------------------------------
# 14. production OHLCV row mapping — volume column must be populated for RVOL
# ---------------------------------------------------------------------------

from generate_snapshots import _build_ohlcv_rows

ohlcv_rows = _build_ohlcv_rows(kr_fixture(), us_fixture(), "2026-04-17")
kr_row = next(row for row in ohlcv_rows if row[0] == "005930")
us_row = next(row for row in ohlcv_rows if row[0] == "NVDA")

check("ohlcv rows: KR volume is populated",
      kr_row[6] == 12_345_678,
      f"row={kr_row}")
check("ohlcv rows: KR amount is preserved",
      kr_row[7] == 1e12,
      f"row={kr_row}")
check("ohlcv rows: US volume is populated",
      us_row[6] == 98_765_432,
      f"row={us_row}")
check("ohlcv rows: US amount/value traded is preserved",
      us_row[7] == 20e9,
      f"row={us_row}")
check("ohlcv rows: KR non-top-gainer universe row included",
      any(row[0] == "000660" and row[6] == 3_210_000 for row in ohlcv_rows))
check("ohlcv rows: US non-top-gainer universe row included",
      any(row[0] == "AAPL" and row[6] == 45_000_000 for row in ohlcv_rows))


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
