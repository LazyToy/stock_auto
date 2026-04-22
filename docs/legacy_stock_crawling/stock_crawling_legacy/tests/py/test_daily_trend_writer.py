"""
TDD test: daily_trend_writer row serialization.

Validates the *pure* transformation from a trend snapshot dict (as produced
by test_market_trend.kr_trend_snapshot / us_trend_snapshot) into a flat row
ready for Google Sheets append. No network, no gspread.

Run
---
    ./stock_crawling/Scripts/python.exe test_daily_trend_writer.py
"""
from __future__ import annotations

import sys

import pandas as pd

from daily_trend_writer import (
    KR_HEADERS,
    US_HEADERS,
    kr_snapshot_to_row,
    us_snapshot_to_row,
    format_keywords,
)

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = PASS if cond else FAIL
    results.append(bool(cond))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Fixtures — mirror the shape emitted by test_market_trend.*_trend_snapshot
# ---------------------------------------------------------------------------

def make_kr_snap() -> dict:
    return dict(
        date="2026-04-12",
        total=2721, up=2030, down=447, flat=244,
        breadth=0.5818,
        kospi_breadth=0.5842,
        kosdaq_breadth=0.5805,
        top20_volume_concentration=0.466,
        surge15_count=41, drop15_count=1,
        limit_up=15, limit_down=0,
        cap_weighted_change=1.52,
        top_gainers=pd.DataFrame([
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI",
             "ChagesRatio": 29.90, "Amount": 1.0e11},
        ]),
        top_losers=pd.DataFrame([
            {"Code": "111111", "Name": "망한회사", "Market": "KOSDAQ",
             "ChagesRatio": -18.50, "Amount": 1.0e9},
        ]),
        top_volume=pd.DataFrame([
            {"Code": "373220", "Name": "LG에너지솔루션", "Market": "KOSPI",
             "ChagesRatio": 3.20, "Amount": 5.0e12},
        ]),
    )


def make_us_snap() -> dict:
    sectors = pd.DataFrame(
        {
            "count": [30, 25, 20],
            "avg_change": [1.88, 0.50, -2.16],
            "total_volume": [1.0e10, 1.0e10, 1.0e10],
            "advancing": [20, 12, 5],
            "advance_pct": [0.67, 0.48, 0.25],
        },
        index=pd.Index(
            ["Energy Minerals", "Finance", "Health Services"],
            name="sector",
        ),
    )
    return dict(
        date="2026-04-12",
        total=2000, up=723, down=1265, flat=12,
        breadth=-0.2710,
        cap_weighted_change=-0.04,
        surge8_count=44, drop8_count=20,
        sectors=sectors,
        top_gainers=pd.DataFrame([
            {"ticker": "ACME", "name": "Acme Inc", "sector": "Finance",
             "change": 35.20, "volume_value": 1.0e8, "market_cap": 5.0e8},
        ]),
        top_losers=pd.DataFrame([
            {"ticker": "LOSR", "name": "Loser Corp", "sector": "Technology Services",
             "change": -22.10, "volume_value": 5.0e7, "market_cap": 2.0e8},
        ]),
        top_volume=pd.DataFrame([
            {"ticker": "NVDA", "name": "NVIDIA", "sector": "Electronic Technology",
             "change": 2.57, "volume_value": 3.027e10},
        ]),
    )


# ---------------------------------------------------------------------------
# KR row assertions
# ---------------------------------------------------------------------------

kr_row = kr_snapshot_to_row(make_kr_snap())

check("KR: row length matches headers",
      len(kr_row) == len(KR_HEADERS),
      f"headers={len(KR_HEADERS)} row={len(kr_row)}")

check("KR: headers are unique (no typos)",
      len(set(KR_HEADERS)) == len(KR_HEADERS))

check("KR: date is first column",
      kr_row[0] == "2026-04-12")

check("KR: scalar counts stored as int",
      all(isinstance(kr_row[KR_HEADERS.index(c)], int)
          for c in ["총종목", "상승", "하락", "보합",
                    "급등15_개수", "급락15_개수", "상한가", "하한가"]))

check("KR: whole-market breadth is a percent (rounded 2dp)",
      kr_row[KR_HEADERS.index("전체_breadth(%)")] == 58.18)

check("KR: KOSPI / KOSDAQ breadth split into separate columns",
      kr_row[KR_HEADERS.index("KOSPI_breadth(%)")] == 58.42
      and kr_row[KR_HEADERS.index("KOSDAQ_breadth(%)")] == 58.05)

check("KR: cap-weighted change passes through without re-scaling",
      kr_row[KR_HEADERS.index("시총가중변동(%)")] == 1.52)

check("KR: top-20 거래대금 concentration as percent",
      kr_row[KR_HEADERS.index("TOP20_거래대금비중(%)")] == 46.60)

check("KR: top gainer name + pct from top_gainers[0]",
      kr_row[KR_HEADERS.index("최대상승종목")] == "삼성전자"
      and kr_row[KR_HEADERS.index("최대상승률(%)")] == 29.90)

check("KR: top loser name + pct from top_losers[0]",
      kr_row[KR_HEADERS.index("최대하락종목")] == "망한회사"
      and kr_row[KR_HEADERS.index("최대하락률(%)")] == -18.50)

check("KR: top volume name + amount converted to 억원",
      kr_row[KR_HEADERS.index("최대거래대금종목")] == "LG에너지솔루션"
      and kr_row[KR_HEADERS.index("최대거래대금(억원)")] == 50000.0)


# ---------------------------------------------------------------------------
# US row assertions
# ---------------------------------------------------------------------------

us_row = us_snapshot_to_row(make_us_snap())

check("US: row length matches headers",
      len(us_row) == len(US_HEADERS),
      f"headers={len(US_HEADERS)} row={len(us_row)}")

check("US: headers are unique",
      len(set(US_HEADERS)) == len(US_HEADERS))

check("US: date is first column",
      us_row[0] == "2026-04-12")

check("US: breadth converted to percent (negative preserved)",
      us_row[US_HEADERS.index("breadth(%)")] == -27.10)

check("US: cap_weighted passes through",
      us_row[US_HEADERS.index("cap_weighted(%)")] == -0.04)

check("US: surge/drop counts as int",
      us_row[US_HEADERS.index("surge8_count")] == 44
      and us_row[US_HEADERS.index("drop8_count")] == 20)

check("US: top gainer ticker + pct",
      us_row[US_HEADERS.index("top_gainer")] == "ACME"
      and us_row[US_HEADERS.index("top_gainer(%)")] == 35.20)

check("US: top loser ticker + pct",
      us_row[US_HEADERS.index("top_loser")] == "LOSR"
      and us_row[US_HEADERS.index("top_loser(%)")] == -22.10)

check("US: top volume ticker + $B conversion",
      us_row[US_HEADERS.index("top_volume")] == "NVDA"
      and us_row[US_HEADERS.index("top_volume($B)")] == 30.27)

check("US: sector leader = first row of sectors (already sorted desc)",
      us_row[US_HEADERS.index("sector_leader")] == "Energy Minerals"
      and us_row[US_HEADERS.index("sector_leader_avg(%)")] == 1.88)

check("US: sector laggard = last row of sectors",
      us_row[US_HEADERS.index("sector_laggard")] == "Health Services"
      and us_row[US_HEADERS.index("sector_laggard_avg(%)")] == -2.16)


# ---------------------------------------------------------------------------
# format_keywords pure-function tests
# ---------------------------------------------------------------------------

check("format_keywords: empty list returns empty string",
      format_keywords([]) == "")

check("format_keywords: single tuple returns 'token(n)'",
      format_keywords([("token", 5)]) == "token(5)")

check("format_keywords: multiple tuples joined with ', '",
      format_keywords([("a", 10), ("b", 5), ("c", 1)]) == "a(10), b(5), c(1)")

check("format_keywords: preserves Korean tokens unchanged",
      format_keywords([("반도체", 12)]) == "반도체(12)")

check("format_keywords: order preserved (not sorted)",
      format_keywords([("z", 1), ("a", 99)]) == "z(1), a(99)")


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
