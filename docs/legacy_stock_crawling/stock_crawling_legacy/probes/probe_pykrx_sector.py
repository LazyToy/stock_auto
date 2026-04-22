"""Probe pykrx.stock.get_market_sector_classifications directly."""
from __future__ import annotations

import inspect
import traceback
from datetime import datetime, timedelta

from pykrx import stock

fn = stock.get_market_sector_classifications

print("signature:", inspect.signature(fn))
print("docstring:")
print(inspect.getdoc(fn) or "  (no docstring)")

# Try today, then walk back up to 10 days in case market was closed
today = datetime.now()
for delta in range(0, 10):
    d = (today - timedelta(days=delta)).strftime("%Y%m%d")
    for market in ("KOSPI", "KOSDAQ", "ALL"):
        print(f"\n--- try date={d} market={market} ---")
        try:
            df = fn(d, market=market)
        except TypeError:
            try:
                df = fn(d, market)
            except Exception:
                traceback.print_exc(limit=2)
                continue
        except Exception:
            traceback.print_exc(limit=2)
            continue
        print(f"  OK rows={len(df)}")
        print(f"  columns={list(df.columns)}")
        print(f"  index name={df.index.name}")
        print("  first 5:")
        print(df.head(5).to_string())
        if len(df) > 0:
            print()
            print("  <<< WORKING PATH — stop probing >>>")
            raise SystemExit(0)

print("\n[!] No working date/market combo found")
