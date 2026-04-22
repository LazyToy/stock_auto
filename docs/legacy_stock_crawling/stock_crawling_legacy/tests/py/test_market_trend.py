"""
Daily market trend snapshot test.

Goal
----
The existing scrapers capture *individual* surge/high-volume tickers but do not
aggregate into a market-level "what happened today" view. This test:

1. Verifies both data pipelines (KR via FinanceDataReader, US via TradingView)
   still respond and return the columns production relies on.
2. Computes trend aggregates the original scrapers don't: advance/decline
   breadth, volume concentration, top sector movers, extreme-move clusters.
3. Prints a single daily snapshot to stdout. Read-only — does not touch
   Google Sheets.

Run
---
    ./stock_crawling/Scripts/python.exe tests/py/test_market_trend.py

Set PYTHONIOENCODING=utf-8 on Windows consoles if Korean text shows as '?'.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# market_trend.py 모듈에서 모든 핵심 함수를 re-export
from market_trend import (  # noqa: F401
    Report,
    CheckResult,
    kr_pipeline_checks,
    kr_trend_snapshot,
    us_pipeline_checks,
    us_trend_snapshot,
    fetch_kr,
    fetch_us,
    REQUIRED_KR_COLS,
    PASS,
    FAIL,
    INFO,
)

from datetime import datetime


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def print_kr(snap: dict) -> None:
    print()
    print("=" * 72)
    print(f"  KR MARKET SNAPSHOT  {snap['date']}")
    print("=" * 72)
    print(f"listed={snap['total']:>5}  up={snap['up']:>4}  down={snap['down']:>4}  flat={snap['flat']:>4}")
    print(f"breadth(KOSPI+KOSDAQ) = {snap['breadth']:+.2%}  |  "
          f"KOSPI {snap['kospi_breadth']:+.2%}  KOSDAQ {snap['kosdaq_breadth']:+.2%}")
    print(f"cap-weighted change   = {snap['cap_weighted_change']:+.2f}%")
    print(f"top-20 volume share   = {snap['top20_volume_concentration']:.1%}  (of total 거래대금)")
    print(f"surge  >=+15% : {snap['surge15_count']:>3}   limit-up   >=+29.5% : {snap['limit_up']}")
    print(f"drop   <=-15% : {snap['drop15_count']:>3}   limit-down <=-29.5% : {snap['limit_down']}")
    print()
    print("-- top 5 gainers --")
    for _, row in snap["top_gainers"].head(5).iterrows():
        print(f"  {row['Market']:6s} {row['Code']:6s} {row['Name'][:14]:14s} "
              f"{row['ChagesRatio']:+6.2f}%  amt={row['Amount']/1e8:>8,.0f}억")
    print("-- top 5 losers --")
    for _, row in snap["top_losers"].head(5).iterrows():
        print(f"  {row['Market']:6s} {row['Code']:6s} {row['Name'][:14]:14s} "
              f"{row['ChagesRatio']:+6.2f}%  amt={row['Amount']/1e8:>8,.0f}억")
    print("-- top 5 by 거래대금 --")
    for _, row in snap["top_volume"].head(5).iterrows():
        print(f"  {row['Market']:6s} {row['Code']:6s} {row['Name'][:14]:14s} "
              f"{row['ChagesRatio']:+6.2f}%  amt={row['Amount']/1e8:>8,.0f}억")


def print_us(snap: dict) -> None:
    print()
    print("=" * 72)
    print(f"  US MARKET SNAPSHOT  {snap['date']}")
    print("=" * 72)
    print(f"scanned={snap['total']:>5}  up={snap['up']:>4}  down={snap['down']:>4}  flat={snap['flat']:>4}")
    print(f"breadth            = {snap['breadth']:+.2%}")
    print(f"cap-weighted change= {snap['cap_weighted_change']:+.2f}%")
    print(f"surge >=+8%: {snap['surge8_count']:>3}   drop <=-8%: {snap['drop8_count']:>3}")
    print()
    print("-- sector rotation (avg change, desc) --")
    for sector, row in snap["sectors"].iterrows():
        print(f"  {sector[:28]:28s} n={int(row['count']):>4}  "
              f"avg={row['avg_change']:+6.2f}%  adv={row['advance_pct']:.0%}  "
              f"vol=${row['total_volume']/1e9:>6.1f}B")
    print()
    print("-- top 5 gainers --")
    for _, row in snap["top_gainers"].head(5).iterrows():
        print(f"  {row['ticker']:6s} {row['name'][:28]:28s} "
              f"{row['change']:+6.2f}%  vol=${row['volume_value']/1e6:>7.1f}M  "
              f"cap=${row['market_cap']/1e9:>6.2f}B")
    print("-- top 5 losers --")
    for _, row in snap["top_losers"].head(5).iterrows():
        print(f"  {row['ticker']:6s} {row['name'][:28]:28s} "
              f"{row['change']:+6.2f}%  vol=${row['volume_value']/1e6:>7.1f}M")
    print("-- top 5 by $volume --")
    for _, row in snap["top_volume"].head(5).iterrows():
        print(f"  {row['ticker']:6s} {row['name'][:28]:28s} "
              f"{row['change']:+6.2f}%  vol=${row['volume_value']/1e9:>6.2f}B")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    report = Report()

    print(f"{INFO} Python: {sys.version.split()[0]}")
    print(f"{INFO} Running at: {datetime.now().isoformat(timespec='seconds')}")
    print()
    print("### KR pipeline checks ###")
    kr_df = kr_pipeline_checks(report)

    print()
    print("### US pipeline checks ###")
    us_df = us_pipeline_checks(report)

    if kr_df is not None:
        print_kr(kr_trend_snapshot(kr_df))
    if us_df is not None and not us_df.empty:
        print_us(us_trend_snapshot(us_df))

    print()
    print("=" * 72)
    passed = sum(1 for c in report.checks if c.passed)
    total = len(report.checks)
    print(f"  RESULT: {passed}/{total} checks passed")
    print("=" * 72)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

