"""
KRX 400 디버그: 세션 쿠키 획득 후 재시도 + 다양한 UA + OTP 플로우 시도.
"""
from __future__ import annotations

import traceback
from datetime import datetime

import requests

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DATA_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
LANDING = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020506"
TODAY = datetime.now().strftime("%Y%m%d")


def probe(label: str, sess: requests.Session, data: dict):
    print(f"\n--- {label} ---")
    try:
        r = sess.post(DATA_URL, data=data, timeout=30)
        print(f"  status={r.status_code}  content-type={r.headers.get('content-type')}")
        print(f"  cookies now: {list(sess.cookies.keys())}")
        print(f"  body[0:300]: {r.text[:300]!r}")
        if r.status_code == 200:
            try:
                j = r.json()
                keys = list(j.keys())
                print(f"  JSON keys: {keys}")
                for k in keys:
                    v = j[k]
                    if isinstance(v, list):
                        print(f"    {k}: list len={len(v)}")
                        if v and isinstance(v[0], dict):
                            print(f"      first row: {v[0]}")
            except Exception as e:
                print(f"  JSON parse failed: {e}")
    except Exception:
        traceback.print_exc(limit=2)


# -------- Attempt 1: bare session, Mozilla UA --------
print("=" * 60)
print("ATTEMPT 1: bare session, Mozilla UA, POST directly")
print("=" * 60)
s1 = requests.Session()
s1.headers.update({"User-Agent": "Mozilla/5.0"})
probe("direct POST", s1, {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
    "trdDd": TODAY,
    "mktId": "STK",
})

# -------- Attempt 2: hit landing first, then POST with Referer --------
print()
print("=" * 60)
print("ATTEMPT 2: visit landing page first (session cookie), then POST")
print("=" * 60)
s2 = requests.Session()
s2.headers.update({"User-Agent": CHROME_UA})
try:
    r0 = s2.get(LANDING, timeout=30)
    print(f"landing status={r0.status_code}  cookies={list(s2.cookies.keys())}")
except Exception:
    traceback.print_exc(limit=2)

s2.headers.update({
    "Referer": LANDING,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://data.krx.co.kr",
})
probe("POST after landing", s2, {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
    "trdDd": TODAY,
    "mktId": "STK",
})

# -------- Attempt 3: pykrx's exact headers & flow --------
print()
print("=" * 60)
print("ATTEMPT 3: replicate pykrx Post class exactly")
print("=" * 60)
s3 = requests.Session()
s3.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
})
probe("pykrx replica", s3, {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
    "trdDd": TODAY,
    "mktId": "STK",
})

# -------- Attempt 4: test a different known-good bld (market cap) --------
print()
print("=" * 60)
print("ATTEMPT 4: alternative bld (market cap daily) to isolate bld vs protocol")
print("=" * 60)
s4 = requests.Session()
s4.headers.update({
    "User-Agent": CHROME_UA,
    "Referer": LANDING,
})
probe("market-cap bld", s4, {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
    "mktId": "STK",
    "trdDd": TODAY,
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
})
