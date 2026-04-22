"""
주간 테마 트렌드 집계 테스트.
Run: stock_crawling/Scripts/python.exe tests/py/test_theme_trend.py
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[bool] = []
def check(name: str, cond: bool, detail: str = "") -> None:
    results.append(bool(cond))
    print(f"{PASS if cond else FAIL} {name}" + (f" - {detail}" if detail else ""))


def test_weekly_aggregate_empty():
    from theme_trend import aggregate_weekly
    assert aggregate_weekly([], prev_week_frequencies={}) == []
    check("aggregate_weekly empty → []", True)

def test_weekly_aggregate_new_sector():
    from theme_trend import aggregate_weekly
    daily = [
        {"sector": "2차전지", "avg_change": 7.0, "ticker_count": 3,
         "representatives": ["A","B","C"], "keywords_top5": [("리튬", 3)]},
        {"sector": "2차전지", "avg_change": 5.0, "ticker_count": 4,
         "representatives": ["A","B","D"], "keywords_top5": [("유럽", 2)]},
    ]
    rows = aggregate_weekly(daily, prev_week_frequencies={})
    check("new_sector: 1 row", len(rows) == 1)
    check("new_sector: sector", rows[0]["sector"] == "2차전지")
    check("new_sector: frequency=2", rows[0]["frequency"] == 2, str(rows[0].get("frequency")))
    check("new_sector: wow=NEW", rows[0]["wow_change"] == "NEW", repr(rows[0].get("wow_change")))

def test_weekly_aggregate_wow_increase():
    from theme_trend import aggregate_weekly
    daily = [{"sector": "바이오", "avg_change": 5.0, "ticker_count": 3,
              "representatives": [], "keywords_top5": []}] * 5
    rows = aggregate_weekly(daily, prev_week_frequencies={"바이오": 2})
    check("wow_increase: ▲ +3", rows[0]["wow_change"] == "▲ +3", repr(rows[0].get("wow_change")))

def test_weekly_aggregate_wow_decrease():
    from theme_trend import aggregate_weekly
    daily = [{"sector": "반도체", "avg_change": -3.0, "ticker_count": 3,
              "representatives": [], "keywords_top5": []}] * 2
    rows = aggregate_weekly(daily, prev_week_frequencies={"반도체": 4})
    check("wow_decrease: ▼ -2", rows[0]["wow_change"] == "▼ -2", repr(rows[0].get("wow_change")))

def test_weekly_aggregate_wow_flat():
    from theme_trend import aggregate_weekly
    daily = [{"sector": "철강", "avg_change": 2.0, "ticker_count": 3,
              "representatives": ["X"], "keywords_top5": []}] * 3
    rows = aggregate_weekly(daily, prev_week_frequencies={"철강": 3})
    check("wow_flat: ─ 0", rows[0]["wow_change"] == "─ 0", repr(rows[0].get("wow_change")))

def test_weekly_avg_change():
    from theme_trend import aggregate_weekly
    daily = [
        {"sector": "자동차", "avg_change": 4.0, "ticker_count": 3, "representatives": [], "keywords_top5": []},
        {"sector": "자동차", "avg_change": 6.0, "ticker_count": 3, "representatives": [], "keywords_top5": []},
    ]
    rows = aggregate_weekly(daily, prev_week_frequencies={})
    check("avg_change_pct=5.0", rows[0]["avg_change_pct"] == 5.0, str(rows[0].get("avg_change_pct")))

def test_weekly_row_serialization():
    from theme_trend import weekly_trend_to_sheet_row
    r = {"sector": "IT", "frequency": 3, "wow_change": "▲ +1",
         "avg_change_pct": 6.5, "representatives": ["AAPL","MSFT"],
         "keywords_top5": [("AI", 5), ("반도체", 3)]}
    row = weekly_trend_to_sheet_row("2026-W16", r)
    check("row length=7", len(row) == 7)
    check("row[0]=iso_week", row[0] == "2026-W16")
    check("row[1]=sector", row[1] == "IT")
    check("row[2]=frequency", row[2] == 3)
    check("row[3]=wow_change", row[3] == "▲ +1")
    check("row[6] contains AI(5)", "AI(5)" in row[6])


# ── 이슈 #5 날짜 산정 테스트 ──────────────────────────────────────
def test_last_iso_week_from_sunday():
    """일요일 실행 시 지난주(같은 주 월요일 기준) ISO 주차 반환."""
    import datetime
    from generate_snapshots import _last_iso_week
    # 2026-04-19 = Sunday (weekday=6), 지난주 = W16 (Apr 13~17)
    sunday = datetime.datetime(2026, 4, 19)
    check("Sunday(4/19) weekday==6", sunday.weekday() == 6)
    result = _last_iso_week(sunday)
    check("Sunday → 2026-W16", result == "2026-W16", f"got {result!r}")


def test_last_iso_week_from_monday():
    """월요일 실행 시 지난주(7일 전 월요일 기준) ISO 주차 반환."""
    import datetime
    from generate_snapshots import _last_iso_week
    # 2026-04-20 = Monday (weekday=0), 지난주 = W16 (Apr 13~17)
    monday = datetime.datetime(2026, 4, 20)
    check("Monday(4/20) weekday==0", monday.weekday() == 0)
    result = _last_iso_week(monday)
    check("Monday → 2026-W16", result == "2026-W16", f"got {result!r}")


def test_last_iso_week_year_boundary():
    """연말 경계: 2026-01-05(월) → 지난주(2025-W52) 반환."""
    import datetime
    from generate_snapshots import _last_iso_week
    # 2026-01-05 = Monday, 지난주 = 2025-W52 (Dec 22-28? 아니면 Dec 29-Jan 4?)
    # 2025-W52: Dec 22(Mon) ~ Dec 28(Sun), W53: Dec 29 ~ Jan 4
    # 2026-01-05(Mon) 7일 전 = 2025-12-29(Mon) → 2025-W01이 아닌가?
    # isocalendar: 2025-12-29 → 2026-W01 (ISO 규정)
    monday = datetime.datetime(2026, 1, 5)
    check("Jan5 weekday==0", monday.weekday() == 0)
    result = _last_iso_week(monday)
    # 2025-12-29 isocalendar → (2026, 1, 1) because ISO 2026-W01 starts Dec 29
    check("Jan5 Mon → 2026-W01", result == "2026-W01", f"got {result!r}")


test_weekly_aggregate_empty()
test_weekly_aggregate_new_sector()
test_weekly_aggregate_wow_increase()
test_weekly_aggregate_wow_decrease()
test_weekly_aggregate_wow_flat()
test_weekly_avg_change()
test_weekly_row_serialization()
test_last_iso_week_from_sunday()
test_last_iso_week_from_monday()
test_last_iso_week_year_boundary()

passed = sum(results); total = len(results)
print(f"\n{'='*60}\n  RESULT: {passed}/{total} checks passed\n{'='*60}")
sys.exit(0 if passed == total else 1)
