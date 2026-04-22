"""
TDD test: DailyTrendSheet — the gspread I/O layer on top of the row
serializers already covered by test_daily_trend_writer.py.

Uses a hand-written fake gspread client so tests never hit the network.
The fake must raise the *real* gspread exception classes so the
production code can catch them naturally.

Run
---
    ./stock_crawling/Scripts/python.exe test_daily_trend_sheet.py
"""
from __future__ import annotations

import sys

import gspread
import pandas as pd

from daily_trend_writer import (
    KR_HEADERS,
    US_HEADERS,
    NEWS_HEADERS,
    NEWS_TAB,
    DailyTrendSheet,
)


PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Fake gspread client
# ---------------------------------------------------------------------------

class FakeWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.rows: list[list] = []
        self.append_calls: list[dict] = []

    def append_row(self, row, value_input_option=None):
        self.rows.append(list(row))
        self.append_calls.append(
            {"row": list(row), "value_input_option": value_input_option}
        )

    def get_all_values(self):
        return [list(r) for r in self.rows]


class FakeSpreadsheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.worksheets_map: dict[str, FakeWorksheet] = {}
        self.add_calls: list[dict] = []

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self.worksheets_map:
            raise gspread.WorksheetNotFound(title)
        return self.worksheets_map[title]

    def add_worksheet(self, title: str, rows="1000", cols: int = 20) -> FakeWorksheet:
        ws = FakeWorksheet(title)
        self.worksheets_map[title] = ws
        self.add_calls.append({"title": title, "rows": rows, "cols": cols})
        return ws


class FakeClient:
    def __init__(self) -> None:
        self.spreadsheets: dict[str, FakeSpreadsheet] = {}
        self.create_calls: list[str] = []
        self.open_calls: list[str] = []

    def open(self, title: str) -> FakeSpreadsheet:
        self.open_calls.append(title)
        if title not in self.spreadsheets:
            raise gspread.SpreadsheetNotFound(title)
        return self.spreadsheets[title]

    def create(self, title: str) -> FakeSpreadsheet:
        self.create_calls.append(title)
        sh = FakeSpreadsheet(title)
        self.spreadsheets[title] = sh
        return sh


# ---------------------------------------------------------------------------
# Minimal fixtures (smaller than test_daily_trend_writer.py — I/O only)
# ---------------------------------------------------------------------------

def make_kr_snap(date: str = "2026-04-12") -> dict:
    return dict(
        date=date,
        total=100, up=60, down=30, flat=10,
        breadth=0.30, kospi_breadth=0.25, kosdaq_breadth=0.35,
        top20_volume_concentration=0.50,
        surge15_count=5, drop15_count=1,
        limit_up=1, limit_down=0,
        cap_weighted_change=1.25,
        top_gainers=pd.DataFrame([
            {"Code": "A", "Name": "가", "Market": "KOSPI",
             "ChagesRatio": 10.0, "Amount": 1.0e10},
        ]),
        top_losers=pd.DataFrame([
            {"Code": "B", "Name": "나", "Market": "KOSDAQ",
             "ChagesRatio": -5.0, "Amount": 1.0e9},
        ]),
        top_volume=pd.DataFrame([
            {"Code": "C", "Name": "다", "Market": "KOSPI",
             "ChagesRatio": 2.0, "Amount": 5.0e11},
        ]),
    )


def make_us_snap(date: str = "2026-04-12") -> dict:
    sectors = pd.DataFrame(
        {
            "count": [10, 5],
            "avg_change": [2.0, -1.5],
            "total_volume": [1.0e9, 1.0e9],
            "advancing": [7, 2],
            "advance_pct": [0.7, 0.4],
        },
        index=pd.Index(["Finance", "Health Services"], name="sector"),
    )
    return dict(
        date=date, total=100, up=40, down=55, flat=5,
        breadth=-0.15, cap_weighted_change=-0.02,
        surge8_count=3, drop8_count=2,
        sectors=sectors,
        top_gainers=pd.DataFrame([
            {"ticker": "X", "name": "x", "sector": "Finance",
             "change": 12.0, "volume_value": 1.0e8, "market_cap": 1.0e9},
        ]),
        top_losers=pd.DataFrame([
            {"ticker": "Y", "name": "y", "sector": "Health Services",
             "change": -8.0, "volume_value": 5.0e7, "market_cap": 5.0e8},
        ]),
        top_volume=pd.DataFrame([
            {"ticker": "Z", "name": "z", "sector": "Finance",
             "change": 1.0, "volume_value": 2.0e10},
        ]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Title derivation
check(
    "title property uses 시장트렌드_{YYYY}",
    DailyTrendSheet(FakeClient(), 2027).title == "시장트렌드_2027",
)

# Existing workbook reused — do not create
gc1 = FakeClient()
gc1.spreadsheets["시장트렌드_2026"] = FakeSpreadsheet("시장트렌드_2026")
s1 = DailyTrendSheet(gc1, 2026)
sh1 = s1.open_or_create()
check(
    "open_or_create reuses existing workbook without calling create",
    sh1.title == "시장트렌드_2026" and gc1.create_calls == [],
)

# Missing workbook is created
gc2 = FakeClient()
s2 = DailyTrendSheet(gc2, 2026)
sh2 = s2.open_or_create()
check(
    "open_or_create creates missing workbook with correct title",
    sh2.title == "시장트렌드_2026"
    and gc2.create_calls == ["시장트렌드_2026"],
)

# KR append — tab creation + header row
gc3 = FakeClient()
s3 = DailyTrendSheet(gc3, 2026)
wrote_kr = s3.append_kr_snapshot(make_kr_snap())
sh3 = gc3.spreadsheets["시장트렌드_2026"]
ws3 = sh3.worksheets_map.get("KR_일별")
check("KR append creates tab named KR_일별",
      ws3 is not None)
check("KR tab first row equals KR_HEADERS",
      ws3 is not None and ws3.rows[0] == KR_HEADERS)
check("KR snapshot appended as row 2",
      ws3 is not None and len(ws3.rows) == 2 and ws3.rows[1][0] == "2026-04-12")
check("KR append returns True on new write",
      wrote_kr is True)
check("KR data append uses USER_ENTERED",
      ws3 is not None and ws3.append_calls[-1]["value_input_option"] == "USER_ENTERED")

# KR dedup — same date is a no-op
wrote_dup = s3.append_kr_snapshot(make_kr_snap())
check("KR duplicate-date append returns False",
      wrote_dup is False)
check("KR duplicate-date does not add a new row",
      ws3 is not None
      and sum(1 for r in ws3.rows[1:] if r and r[0] == "2026-04-12") == 1)

# KR append with a new date succeeds
wrote_new = s3.append_kr_snapshot(make_kr_snap(date="2026-04-13"))
check("KR append with new date returns True",
      wrote_new is True)
check("KR tab has exactly 2 data rows after 2 distinct dates",
      ws3 is not None and len(ws3.rows) == 3)

# US append — tab creation + header row + USER_ENTERED
gc4 = FakeClient()
s4 = DailyTrendSheet(gc4, 2026)
wrote_us = s4.append_us_snapshot(make_us_snap())
sh4 = gc4.spreadsheets["시장트렌드_2026"]
ws4 = sh4.worksheets_map.get("US_일별")
check("US append creates tab named US_일별",
      ws4 is not None)
check("US tab first row equals US_HEADERS",
      ws4 is not None and ws4.rows[0] == US_HEADERS)
check("US snapshot appended as row 2",
      ws4 is not None and len(ws4.rows) == 2 and ws4.rows[1][0] == "2026-04-12")
check("US append returns True on new write",
      wrote_us is True)
check("US data append uses USER_ENTERED",
      ws4 is not None and ws4.append_calls[-1]["value_input_option"] == "USER_ENTERED")

# US dedup
wrote_us_dup = s4.append_us_snapshot(make_us_snap())
check("US duplicate-date append returns False",
      wrote_us_dup is False)

# KR and US coexist in the same workbook
gc5 = FakeClient()
s5 = DailyTrendSheet(gc5, 2026)
s5.append_kr_snapshot(make_kr_snap())
s5.append_us_snapshot(make_us_snap())
sh5 = gc5.spreadsheets["시장트렌드_2026"]
check("single workbook hosts both KR_일별 and US_일별",
      "KR_일별" in sh5.worksheets_map
      and "US_일별" in sh5.worksheets_map)

# open() is called only once across multiple appends (no re-open thrash)
gc6 = FakeClient()
gc6.spreadsheets["시장트렌드_2026"] = FakeSpreadsheet("시장트렌드_2026")
s6 = DailyTrendSheet(gc6, 2026)
s6.append_kr_snapshot(make_kr_snap())
s6.append_us_snapshot(make_us_snap())
s6.append_kr_snapshot(make_kr_snap(date="2026-04-13"))
check("workbook is opened only once across multiple appends",
      len(gc6.open_calls) == 1,
      f"open_calls={gc6.open_calls}")

# ---------------------------------------------------------------------------
# append_news_row tests
# ---------------------------------------------------------------------------

# NEWS tab created with correct headers on first call
gc_n1 = FakeClient()
s_n1 = DailyTrendSheet(gc_n1, 2026)
wrote_n1 = s_n1.append_news_row(
    "2026-04-12",
    [("반도체", 12), ("AI", 8)],
    [("tech", 10), ("earnings", 5)],
    "시장 전반 상승세",
)
sh_n1 = gc_n1.spreadsheets["시장트렌드_2026"]
ws_n1 = sh_n1.worksheets_map.get(NEWS_TAB)
check("NEWS append creates tab named 뉴스요약",
      ws_n1 is not None)
check("NEWS tab first row equals NEWS_HEADERS",
      ws_n1 is not None and ws_n1.rows[0] == NEWS_HEADERS)
check("NEWS append returns True on new write",
      wrote_n1 is True)

# Row content: [date, kr_str, us_str, narrative]
check("NEWS row has date in col 0",
      ws_n1 is not None and ws_n1.rows[1][0] == "2026-04-12")
check("NEWS row has formatted KR keywords in col 1",
      ws_n1 is not None and ws_n1.rows[1][1] == "반도체(12), AI(8)")
check("NEWS row has formatted US keywords in col 2",
      ws_n1 is not None and ws_n1.rows[1][2] == "tech(10), earnings(5)")
check("NEWS row has narrative in col 3",
      ws_n1 is not None and ws_n1.rows[1][3] == "시장 전반 상승세")

# value_input_option must be USER_ENTERED on data row
check("NEWS data append uses USER_ENTERED",
      ws_n1 is not None
      and ws_n1.append_calls[-1]["value_input_option"] == "USER_ENTERED")

# Dedup: same date returns False, no extra row
wrote_n1_dup = s_n1.append_news_row(
    "2026-04-12",
    [("중복", 1)],
    [],
    "중복 내러티브",
)
check("NEWS duplicate-date append returns False",
      wrote_n1_dup is False)
check("NEWS duplicate-date does not add a new row",
      ws_n1 is not None
      and sum(1 for r in ws_n1.rows[1:] if r and r[0] == "2026-04-12") == 1)

# Different date is allowed — both rows present
wrote_n1_new = s_n1.append_news_row(
    "2026-04-13",
    [],
    [],
    "다음날 요약",
)
check("NEWS append with new date returns True",
      wrote_n1_new is True)
check("NEWS tab has exactly 2 data rows after 2 distinct dates",
      ws_n1 is not None and len(ws_n1.rows) == 3)

# Empty keyword lists write empty strings (not errors)
gc_n2 = FakeClient()
s_n2 = DailyTrendSheet(gc_n2, 2026)
wrote_n2 = s_n2.append_news_row("2026-04-12", [], [], "내러티브만")
sh_n2 = gc_n2.spreadsheets["시장트렌드_2026"]
ws_n2 = sh_n2.worksheets_map.get(NEWS_TAB)
check("NEWS row with empty keyword lists writes empty strings for KR and US",
      ws_n2 is not None
      and ws_n2.rows[1][1] == ""
      and ws_n2.rows[1][2] == "")
check("NEWS row with empty keyword lists still writes correctly",
      wrote_n2 is True)

# Empty narrative still writes
gc_n3 = FakeClient()
s_n3 = DailyTrendSheet(gc_n3, 2026)
wrote_n3 = s_n3.append_news_row("2026-04-12", [("a", 1)], [("b", 2)], "")
sh_n3 = gc_n3.spreadsheets["시장트렌드_2026"]
ws_n3 = sh_n3.worksheets_map.get(NEWS_TAB)
check("NEWS row with empty narrative still writes",
      wrote_n3 is True and ws_n3 is not None and ws_n3.rows[1][3] == "")

# NEWS tab does not interfere with KR/US tabs in the same instance
gc_n4 = FakeClient()
s_n4 = DailyTrendSheet(gc_n4, 2026)
s_n4.append_kr_snapshot(make_kr_snap())
s_n4.append_us_snapshot(make_us_snap())
s_n4.append_news_row("2026-04-12", [("키워드", 3)], [("keyword", 2)], "복합 테스트")
sh_n4 = gc_n4.spreadsheets["시장트렌드_2026"]
check("NEWS tab coexists with KR_일별 and US_일별 in same workbook",
      "KR_일별" in sh_n4.worksheets_map
      and "US_일별" in sh_n4.worksheets_map
      and NEWS_TAB in sh_n4.worksheets_map)
ws_kr_n4 = sh_n4.worksheets_map["KR_일별"]
ws_us_n4 = sh_n4.worksheets_map["US_일별"]
ws_news_n4 = sh_n4.worksheets_map[NEWS_TAB]
check("NEWS tab does not affect KR tab row count",
      len(ws_kr_n4.rows) == 2)
check("NEWS tab does not affect US tab row count",
      len(ws_us_n4.rows) == 2)
check("NEWS tab has its own independent data row",
      len(ws_news_n4.rows) == 2 and ws_news_n4.rows[1][0] == "2026-04-12")


passed = sum(1 for r in results if r)
total = len(results)
print()
print("=" * 60)
print(f"  RESULT: {passed}/{total} checks passed")
print("=" * 60)
sys.exit(0 if passed == total else 1)
