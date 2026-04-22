"""
market_trend — KR/US 시장 트렌드 스냅샷 빌더.

tests/py/test_market_trend.py 에 있던 핵심 함수들을 production 모듈로 분리.
generate_snapshots.py 가 테스트 파일 대신 이 모듈에서 import 한다.

공개 인터페이스
--------------
* ``kr_trend_snapshot(df)`` — KR 시장 스냅샷 dict 생성
* ``us_trend_snapshot(df)`` — US 시장 스냅샷 dict 생성
* ``kr_pipeline_checks(r)`` — KR FDR 파이프라인 검증 + DataFrame 반환
* ``us_pipeline_checks(r)`` — US TradingView 파이프라인 검증 + DataFrame 반환
* ``Report`` — 검증 결과 수집 dataclass
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import pandas as pd

from src.crawling.us_stock_scraper import decode_tv_row

# ---------------------------------------------------------------------------
# 보고 도구
# ---------------------------------------------------------------------------

REQUIRED_KR_COLS = ["Code", "Name", "Market", "Close", "ChagesRatio", "Amount", "Marcap"]
PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    data: Any = None


@dataclass
class Report:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "", data: Any = None) -> CheckResult:
        cr = CheckResult(name, passed, detail, data)
        self.checks.append(cr)
        tag = PASS if passed else FAIL
        print(f"{tag} {name}" + (f" — {detail}" if detail else ""))
        return cr

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)


# ---------------------------------------------------------------------------
# KR market (FinanceDataReader)
# ---------------------------------------------------------------------------

def fetch_kr() -> pd.DataFrame:
    """KRX 전종목 데이터 조회."""
    import importlib
    fdr = importlib.import_module("FinanceDataReader")
    return fdr.StockListing("KRX")


def kr_pipeline_checks(r: Report) -> pd.DataFrame | None:
    """KR FDR 파이프라인 검증 + KOSPI/KOSDAQ DataFrame 반환."""
    try:
        df = fetch_kr()
    except Exception as e:
        r.add("KR: fdr.StockListing('KRX') fetch", False, f"{e}")
        return None

    missing = [c for c in REQUIRED_KR_COLS if c not in df.columns]
    r.add(
        "KR: required columns present",
        not missing,
        f"missing={missing}" if missing else f"rows={len(df)}",
    )
    if missing:
        return None

    df = cast(pd.DataFrame, df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy())
    df["ChagesRatio"] = cast(pd.Series, pd.to_numeric(df["ChagesRatio"], errors="coerce")).fillna(0)
    df["Amount"] = cast(pd.Series, pd.to_numeric(df["Amount"], errors="coerce")).fillna(0)
    if "Volume" in df.columns:
        df["Volume"] = cast(pd.Series, pd.to_numeric(df["Volume"], errors="coerce")).fillna(0)
    else:
        df["Volume"] = 0
    df["Marcap"] = cast(pd.Series, pd.to_numeric(df["Marcap"], errors="coerce")).fillna(0)

    r.add("KR: KOSPI+KOSDAQ row count > 1500", len(df) > 1500, f"rows={len(df)}")
    r.add(
        "KR: Amount scale looks like KRW (max > 1e10)",
        df["Amount"].max() > 1e10,
        f"max={df['Amount'].max():,.0f}",
    )
    return cast(pd.DataFrame, df)


def kr_trend_snapshot(df: pd.DataFrame) -> dict:
    """KR 시장 breadth + concentration + extreme clusters 스냅샷."""
    n = len(df)
    up = int((df["ChagesRatio"] > 0).sum())
    down = int((df["ChagesRatio"] < 0).sum())
    flat = n - up - down
    breadth = (up - down) / n if n else 0.0

    kospi = df[df["Market"] == "KOSPI"]
    kosdaq = df[df["Market"] == "KOSDAQ"]
    kospi_breadth = ((kospi["ChagesRatio"] > 0).sum() - (kospi["ChagesRatio"] < 0).sum()) / max(len(kospi), 1)
    kosdaq_breadth = ((kosdaq["ChagesRatio"] > 0).sum() - (kosdaq["ChagesRatio"] < 0).sum()) / max(len(kosdaq), 1)

    total_amt = df["Amount"].sum()
    top20 = df.nlargest(20, "Amount")
    concentration = top20["Amount"].sum() / total_amt if total_amt else 0.0

    surge15 = int((df["ChagesRatio"] >= 15).sum())
    drop15 = int((df["ChagesRatio"] <= -15).sum())
    limit_up = int((df["ChagesRatio"] >= 29.5).sum())
    limit_down = int((df["ChagesRatio"] <= -29.5).sum())

    avg_change_weighted = (
        (df["ChagesRatio"] * df["Marcap"]).sum() / df["Marcap"].sum()
        if df["Marcap"].sum() else 0.0
    )

    kr_cols = ["Code", "Name", "Market", "ChagesRatio", "Volume", "Amount"]
    top_gainers = df.nlargest(10, "ChagesRatio")[kr_cols]
    top_losers = df.nsmallest(10, "ChagesRatio")[kr_cols]
    top_volume = df.nlargest(10, "Amount")[kr_cols]
    ohlcv_cols = [c for c in ["Code", "Open", "High", "Low", "Close", "Volume", "Amount"] if c in df.columns]

    return dict(
        date=datetime.now().strftime("%Y-%m-%d"),
        total=n,
        up=up, down=down, flat=flat,
        breadth=breadth,
        kospi_breadth=kospi_breadth,
        kosdaq_breadth=kosdaq_breadth,
        top20_volume_concentration=concentration,
        surge15_count=surge15,
        drop15_count=drop15,
        limit_up=limit_up,
        limit_down=limit_down,
        cap_weighted_change=avg_change_weighted,
        top_gainers=top_gainers,
        top_losers=top_losers,
        top_volume=top_volume,
        ohlcv_rows=df[ohlcv_cols].copy(),
    )


# ---------------------------------------------------------------------------
# US market (TradingView scanner)
# ---------------------------------------------------------------------------

TV_URL = "https://scanner.tradingview.com/america/scan"


def fetch_us(min_volume_usd: float = 0.0, limit: int = 2000) -> pd.DataFrame:
    """TradingView Scanner API 에서 미국 주식 데이터 조회."""
    payload = {
        "filter": [
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
            {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]},
            {"left": "Value.Traded", "operation": "greater", "right": min_volume_usd},
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": [
            "name", "description", "close", "change", "Value.Traded",
            "high", "low", "market_cap_basic", "sector", "volume",
        ],
        "sort": {"sortBy": "Value.Traded", "sortOrder": "desc"},
        "range": [0, limit],
    }
    req = urllib.request.Request(
        TV_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))

    rows = []
    for item in data.get("data", []):
        row = decode_tv_row(item["d"])
        if not row["sector"]:
            row["sector"] = "Unknown"
        rows.append(row)
    return pd.DataFrame(rows)


def us_pipeline_checks(r: Report) -> pd.DataFrame | None:
    """US TradingView 파이프라인 검증 + DataFrame 반환."""
    try:
        df = fetch_us(min_volume_usd=1_000_000, limit=2000)
    except Exception as e:
        r.add("US: TradingView scanner fetch", False, f"{e}")
        return None

    r.add("US: response non-empty", len(df) > 0, f"rows={len(df)}")
    if df.empty:
        return None

    needed = {"ticker", "change", "volume", "volume_value", "sector", "market_cap"}
    missing = needed - set(df.columns)
    r.add("US: required columns present", not missing, f"missing={sorted(missing)}" if missing else "all present")
    if missing:
        return None

    r.add(
        "US: positional decode sanity (close > 0)",
        bool((df["close"] > 0).mean() > 0.95),
        f"pct_positive_close={(df['close'] > 0).mean():.2%}",
    )
    return df


def us_trend_snapshot(df: pd.DataFrame) -> dict:
    """US 시장 breadth + sector rotation + extreme clusters 스냅샷."""
    n = len(df)
    up = int((df["change"] > 0).sum())
    down = int((df["change"] < 0).sum())
    flat = n - up - down
    breadth = (up - down) / n if n else 0.0

    sector_grouped = df.groupby("sector").agg(
        count=("ticker", "size"),
        avg_change=("change", "mean"),
        total_volume=("volume_value", "sum"),
        advancing=("change", lambda s: int((s > 0).sum())),
    )
    sectors = cast(pd.DataFrame, sector_grouped).sort_values(by="avg_change", ascending=False)
    sectors["advance_pct"] = sectors["advancing"] / sectors["count"]

    cap_weighted = (
        (df["change"] * df["market_cap"]).sum() / df["market_cap"].sum()
        if df["market_cap"].sum() else 0.0
    )

    us_cols = ["ticker", "name", "sector", "change", "volume", "volume_value", "market_cap"]
    top_gainers = df.nlargest(10, "change")[us_cols]
    top_losers = df.nsmallest(10, "change")[us_cols]
    top_volume = df.nlargest(10, "volume_value")[us_cols]
    ohlcv_cols = [c for c in ["ticker", "close", "high", "low", "volume", "volume_value"] if c in df.columns]

    surge8 = int((df["change"] >= 8).sum())
    drop8 = int((df["change"] <= -8).sum())

    return dict(
        date=datetime.now().strftime("%Y-%m-%d"),
        total=n,
        up=up, down=down, flat=flat,
        breadth=breadth,
        cap_weighted_change=cap_weighted,
        surge8_count=surge8,
        drop8_count=drop8,
        sectors=sectors,
        top_gainers=top_gainers,
        top_losers=top_losers,
        top_volume=top_volume,
        ohlcv_rows=df[ohlcv_cols].copy(),
    )
