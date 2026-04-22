"""Raw debug: see EXACTLY what KRX returns for MDCSTAT03901."""
from __future__ import annotations

import json
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# --- 1) Direct HTTPS call ---
URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
}

for delta in range(0, 4):
    trd = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
    print(f"\n### direct HTTPS trdDd={trd} mktId=STK ###")
    params = {"bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
              "trdDd": trd, "mktId": "STK"}
    try:
        req = urllib.request.Request(
            URL,
            data=urllib.parse.urlencode(params).encode("utf-8"),
            headers=HEADERS,
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            status = res.status
            body = res.read().decode("utf-8")
            print(f"  HTTP {status}  bytes={len(body)}")
            try:
                payload = json.loads(body)
                print(f"  top-level keys: {list(payload.keys())}")
                for k in payload.keys():
                    v = payload[k]
                    if isinstance(v, list):
                        print(f"    {k}: list len={len(v)}")
                        if v and isinstance(v[0], dict):
                            print(f"      first row keys: {list(v[0].keys())}")
                            print(f"      first row: {v[0]}")
                    else:
                        short = str(v)[:200]
                        print(f"    {k}: {type(v).__name__} = {short}")
            except Exception:
                print("  body preview:")
                print(body[:500])
    except Exception:
        traceback.print_exc(limit=3)


# --- 2) pykrx 업종분류현황 direct ---
print()
print("### pykrx 업종분류현황().fetch(today, 'STK') ###")
try:
    from pykrx.website.krx.market.core import 업종분류현황
    for delta in range(0, 4):
        trd = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
        print(f"\n  -- trd={trd} --")
        df = 업종분류현황().fetch(trd, "STK")
        print(f"  type={type(df).__name__}")
        if hasattr(df, "shape"):
            print(f"  shape={df.shape}")
            if hasattr(df, "columns"):
                print(f"  cols={list(df.columns)[:10]}")
            try:
                print(f"  head:")
                print(df.head(3).to_string())
            except Exception:
                pass
except Exception:
    traceback.print_exc(limit=3)
