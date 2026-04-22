"""
generate_snapshots — daily KR+US market snapshot writer.

This is the orchestration layer that glues together:

  * ``test_market_trend.kr_trend_snapshot`` / ``us_trend_snapshot`` — the
    pure snapshot-builders that already exist.
  * ``daily_trend_writer.DailyTrendSheet`` — the gspread-facing sheet API.

``run_snapshots`` is injectable so ``test_generate_snapshots.py`` can
exercise it without touching pandas pipelines or Google Sheets. The
``main`` function wires in the production sources.

Exit codes
----------
0  — both snapshots written successfully
1  — at least one side failed (see stderr for the trace)
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from typing import Any, Callable

_SheetFactory = Callable[[int], object]
_SnapshotSource = Callable[[], dict]
_NewsSource = Callable[[Any, Any], tuple]
_ThemeSource = Callable[[Any, Any], list]
_MarketFlowFactory = Callable[[int], object]
_WeeklyTrendFactory = Callable[[int], object]
_Clock = Callable[[], datetime]
_OHLCVSink = Callable[[Any, Any, str], None]  # (kr_snap|None, us_snap|None, date_str)
_EarlySignalSource = Callable[[Any, str], list]  # (kr_snap|None, date_str) → signal dicts
_FlowSignalSource = Callable[[Any, str], list]   # (kr_snap|None, date_str) → signal dicts
_NotifierFn = Callable[[Any, list, list, list, int], None]  # (kr_snap, clusters, early_signals, flow_signals, rc)


def _last_iso_week(now: datetime) -> str:
    """
    '지난주' ISO 주차 문자열을 YYYY-Www 형식으로 반환.

    일요일(weekday=6) 실행 시 → 6일 전 (같은 주 월요일) 기준
    월요일(weekday=0) 실행 시 → 7일 전 (지난 주 월요일) 기준

    예: 2026-04-19 (일) → 2026-04-13 (월) → "2026-W16"
        2026-04-20 (월) → 2026-04-13 (월) → "2026-W16"
    """
    import datetime as _dt
    if now.weekday() == 6:          # 일요일
        last_monday = now - _dt.timedelta(days=6)
    else:                           # 월요일(0)
        last_monday = now - _dt.timedelta(days=7)
    iso_cal = last_monday.isocalendar()
    return f"{iso_cal[0]}-W{iso_cal[1]:02d}"


def run_snapshots(
    kr_source: _SnapshotSource,
    us_source: _SnapshotSource,
    sheet_factory: _SheetFactory,
    news_source: _NewsSource | None = None,
    theme_source: _ThemeSource | None = None,
    market_flow_factory: _MarketFlowFactory | None = None,
    weekly_trend_factory: _WeeklyTrendFactory | None = None,
    force_weekly: bool = False,
    clock: _Clock = datetime.now,
    ohlcv_sink: _OHLCVSink | None = None,
    early_signal_source: _EarlySignalSource | None = None,
    flow_signal_source: _FlowSignalSource | None = None,
    notifier: _NotifierFn | None = None,
) -> int:
    """
    Run KR and US snapshot side-by-side and return a unix-style rc.

    Each side is isolated in its own try/except so one failure does not
    skip the other. The sheet factory is tried **first**; if it raises,
    neither data source is called (no point computing a snapshot we can't
    persist).

    When ``news_source`` is supplied it is called after both snapshot
    tasks with ``(kr_snap_or_None, us_snap_or_None)`` and must return
    ``(kr_keywords, us_keywords, narrative)``. The result is appended to
    the workbook's 뉴스요약 tab via ``sheet.append_news_row``. A news
    failure is isolated like the snapshot tasks and flips rc to 1 without
    undoing the KR/US appends that already happened.
    """
    now = clock()
    year = int(now.strftime("%Y"))

    try:
        sheet = sheet_factory(year)
    except Exception:
        print("[generate_snapshots] sheet factory failed:", file=sys.stderr)
        traceback.print_exc(limit=5)
        return 1

    kr_snap: dict | None = None
    kr_ok = False
    try:
        kr_snap = kr_source()
        sheet.append_kr_snapshot(kr_snap)  # type: ignore[attr-defined]
        kr_ok = True
        print("[generate_snapshots] KR snapshot appended")
    except Exception:
        print("[generate_snapshots] KR snapshot failed:", file=sys.stderr)
        traceback.print_exc(limit=5)

    us_snap: dict | None = None
    us_ok = False
    try:
        us_snap = us_source()
        sheet.append_us_snapshot(us_snap)  # type: ignore[attr-defined]
        us_ok = True
        print("[generate_snapshots] US snapshot appended")
    except Exception:
        print("[generate_snapshots] US snapshot failed:", file=sys.stderr)
        traceback.print_exc(limit=5)

    news_ok = True
    if news_source is not None:
        news_ok = False
        try:
            kr_kw, us_kw, narrative = news_source(
                kr_snap if kr_ok else None,
                us_snap if us_ok else None,
            )
            if kr_snap is not None and "date" in kr_snap:
                date_str = str(kr_snap["date"])
            elif us_snap is not None and "date" in us_snap:
                date_str = str(us_snap["date"])
            else:
                date_str = now.strftime("%Y-%m-%d")
            sheet.append_news_row(  # type: ignore[attr-defined]
                date_str, kr_kw, us_kw, narrative,
            )
            news_ok = True
            print("[generate_snapshots] news summary appended")
        except Exception:
            print("[generate_snapshots] news summary failed:", file=sys.stderr)
            traceback.print_exc(limit=5)

    clusters: list = []
    theme_ok = True
    if theme_source is not None:
        theme_ok = False
        try:
            clusters = theme_source(
                kr_snap if kr_ok else None,
                us_snap if us_ok else None,
            )
            # 날짜 파생 — news_source 와 동일 패턴
            if kr_snap is not None and "date" in kr_snap:
                theme_date = str(kr_snap["date"])
            elif us_snap is not None and "date" in us_snap:
                theme_date = str(us_snap["date"])
            else:
                theme_date = now.strftime("%Y-%m-%d")
            if market_flow_factory is not None:
                mf_sheet = market_flow_factory(year)
                count = mf_sheet.append_theme_clusters(  # type: ignore[attr-defined]
                    theme_date, clusters
                )
                print(
                    f"[generate_snapshots] 테마클러스터 {count}건 기록 (날짜: {theme_date})"
                )
            else:
                print(
                    f"[generate_snapshots] 테마클러스터 {len(clusters)}건 집계 "
                    "(market_flow_factory 미설정 — 시트 기록 생략)"
                )
            theme_ok = True
        except Exception:
            print("[generate_snapshots] 테마클러스터 실패:", file=sys.stderr)
            traceback.print_exc(limit=5)

    weekly_ok = True
    if weekly_trend_factory is not None:
        # 매주 일요일(6) 또는 월요일(0) 첫 실행 시에만 지난주 집계. force_weekly=True 면 강제 실행.
        should_run = force_weekly or now.weekday() in (0, 6)
        if should_run:
            weekly_ok = False
            try:
                import datetime as _dt
                mf_week = weekly_trend_factory(year)
                # 이슈 #5 수정: 일요일/월요일 모두 '지난주' 기준 ISO 주차 계산
                iso_week = _last_iso_week(now)
                clusters = _read_weekly_clusters(mf_week, iso_week)
                count = mf_week.append_weekly_trends(  # type: ignore[attr-defined]
                    iso_week, clusters
                )
                print(
                    f"[generate_snapshots] 테마트렌드_주간 {count}건 기록 (주차: {iso_week})"
                )
                weekly_ok = True
            except Exception:
                print("[generate_snapshots] 테마트렌드_주간 실패:", file=sys.stderr)
                traceback.print_exc(limit=5)
        else:
            print(
                f"[generate_snapshots] 테마트렌드_주간 스킵 "
                f"(요일: {now.strftime('%A')}, 일요일/월요일에만 실행)"
            )

    # ── 이슈 #7: 조기신호 감지 (ohlcv_sink 이전 — 당일 거래량이 평균에 섞이지 않도록) ──
    early_signal_ok = True
    early_signals: list = []
    if early_signal_source is not None:
        early_signal_ok = False
        try:
            date_str_es = now.strftime("%Y-%m-%d")
            early_signals = early_signal_source(
                kr_snap if kr_ok else None,
                date_str_es,
            )
            if market_flow_factory is not None:
                mf_es = market_flow_factory(year)
                count = mf_es.append_early_signals(date_str_es, early_signals)  # type: ignore[attr-defined]
                print(f"[generate_snapshots] 조기신호 {count}건 기록 (날짜: {date_str_es})")
            else:
                print(
                    f"[generate_snapshots] 조기신호 {len(early_signals)}건 감지 "
                    "(market_flow_factory 미설정 — 시트 기록 생략)"
                )
            early_signal_ok = True
        except Exception:
            print("[generate_snapshots] 조기신호 실패:", file=sys.stderr)
            traceback.print_exc(limit=5)

    ohlcv_ok = True
    if ohlcv_sink is not None:
        ohlcv_ok = False
        try:
            date_str = now.strftime("%Y-%m-%d")
            ohlcv_sink(
                kr_snap if kr_ok else None,
                us_snap if us_ok else None,
                date_str,
            )
            ohlcv_ok = True
            print(f"[generate_snapshots] OHLCV upsert 완료 ({date_str})")
        except Exception:
            print("[generate_snapshots] OHLCV upsert 실패:", file=sys.stderr)
            traceback.print_exc(limit=5)

    # ── 이슈 #11: 수급전환 감지 ─────────────────────────────────────────────
    flow_signal_ok = True
    flow_signals: list = []
    if flow_signal_source is not None:
        flow_signal_ok = False
        try:
            date_str_fs = now.strftime("%Y-%m-%d")
            flow_signals = flow_signal_source(
                kr_snap if kr_ok else None,
                date_str_fs,
            )
            if market_flow_factory is not None:
                mf_fs = market_flow_factory(year)
                count = mf_fs.append_flow_signals(date_str_fs, flow_signals)  # type: ignore[attr-defined]
                print(f"[generate_snapshots] 수급전환 {count}건 기록 (날짜: {date_str_fs})")
            else:
                print(
                    f"[generate_snapshots] 수급전환 {len(flow_signals)}건 감지 "
                    "(market_flow_factory 미설정 — 시트 기록 생략)"
                )
            flow_signal_ok = True
        except Exception:
            print("[generate_snapshots] 수급전환 실패:", file=sys.stderr)
            traceback.print_exc(limit=5)

    # ── 이슈 #8: Telegram 알림 (마지막 — 파이프라인 rc에 영향 없음) ──────────
    if notifier is not None:
        try:
            rc_so_far = 0 if (kr_ok and us_ok and news_ok and theme_ok
                              and weekly_ok and ohlcv_ok
                              and early_signal_ok and flow_signal_ok) else 1
            notifier(
                kr_snap if kr_ok else None,
                clusters,
                early_signals,
                flow_signals,
                rc_so_far,
            )
            print("[generate_snapshots] Telegram 알림 완료")
        except Exception:
            print("[generate_snapshots] Telegram 알림 실패:", file=sys.stderr)
            traceback.print_exc(limit=5)

    return 0 if (
        kr_ok and us_ok and news_ok and theme_ok and weekly_ok
        and ohlcv_ok and early_signal_ok and flow_signal_ok
    ) else 1


# ---------------------------------------------------------------------------
# Production wiring — not unit-tested, exercised by run_daily.ts
# ---------------------------------------------------------------------------

def _production_kr_source() -> dict:
    """KR 시장 스냅샷 빌더 — market_trend 모듈 사용."""
    import pandas as pd
    import importlib
    from typing import cast
    fdr = importlib.import_module("FinanceDataReader")
    from src.crawling.market_trend import kr_trend_snapshot

    df = cast(pd.DataFrame, fdr.StockListing("KRX"))
    df = cast(pd.DataFrame, df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy())
    df["ChagesRatio"] = cast(pd.Series, pd.to_numeric(df["ChagesRatio"], errors="coerce")).fillna(0)
    df["Amount"] = cast(pd.Series, pd.to_numeric(df["Amount"], errors="coerce")).fillna(0)
    if "Volume" in df.columns:
        df["Volume"] = cast(pd.Series, pd.to_numeric(df["Volume"], errors="coerce")).fillna(0)
    else:
        df["Volume"] = 0
    df["Marcap"] = cast(pd.Series, pd.to_numeric(df["Marcap"], errors="coerce")).fillna(0)
    return kr_trend_snapshot(df)


def _production_us_source() -> dict:
    """US 시장 스냅샷 빌더 — market_trend 모듈 사용."""
    from src.crawling.market_trend import us_pipeline_checks, us_trend_snapshot, Report

    r = Report()
    df = us_pipeline_checks(r)
    if df is None or len(df) == 0:
        raise RuntimeError("US pipeline returned no rows")
    return us_trend_snapshot(df)


def _production_sheet_factory(year: int):
    from src.crawling.daily_trend_writer import DailyTrendSheet, make_sheet_client

    gc = make_sheet_client()
    return DailyTrendSheet(gc, year)


_NEWS_TOP_N_TICKERS = 10
_NEWS_TOP_N_KEYWORDS = 10


def _top_tickers(snap: dict | None, primary: str, fallback: str) -> list[str]:
    """Return up to N tickers from snap['top_gainers'] for news fetching."""
    if snap is None:
        return []
    df = snap.get("top_gainers")
    if df is None or getattr(df, "empty", True):
        return []
    col = primary if primary in df.columns else (
        fallback if fallback in df.columns else None
    )
    if col is None:
        return []
    return [str(c) for c in df[col].head(_NEWS_TOP_N_TICKERS).tolist()]


def _production_news_source(
    kr_snap: dict | None, us_snap: dict | None,
) -> tuple:
    """
    Fetch news titles for the top gainers of each market, aggregate
    keywords, and ask Gemini for a 2-3 sentence narrative. Falls back to
    a deterministic template when the Gemini key is missing.
    """
    from src.crawling.news_fetcher import fetch_kr_titles, fetch_us_titles
    from src.crawling.news_aggregator import extract_keywords, summarize_narrative
    from src.crawling.gemini_client import load_api_key, make_gemini_fn

    kr_codes = _top_tickers(kr_snap, "Code", "code")
    us_codes = _top_tickers(us_snap, "Ticker", "ticker")

    kr_titles = fetch_kr_titles(kr_codes) if kr_codes else []
    us_titles = fetch_us_titles(us_codes) if us_codes else []

    kr_kw = extract_keywords(kr_titles, top_n=_NEWS_TOP_N_KEYWORDS)
    us_kw = extract_keywords(us_titles, top_n=_NEWS_TOP_N_KEYWORDS)

    gemini_fn = make_gemini_fn(load_api_key(".env.local"))
    narrative = summarize_narrative(kr_kw, us_kw, gemini_fn=gemini_fn)

    return kr_kw, us_kw, narrative


def _production_theme_source(
    kr_snap: dict | None, us_snap: dict | None,
) -> list:
    """
    KRX 전종목 데이터에서 테마 클러스터를 집계하여 반환.

    * FDR StockListing('KRX') 로 당일 등락률·거래대금 수집
    * SectorMapKR 로 섹터 분류
    * 임계값(±5%) 이상 종목에 한해 Naver 뉴스 per-ticker 수집 (최대 50종목)
    * theme_cluster.build_theme_clusters 로 클러스터 집계
    """
    import pandas as pd
    import importlib
    from typing import cast
    fdr = importlib.import_module("FinanceDataReader")
    from src.crawling.sector_map_kr import SectorMapKR
    from news_fetcher import fetch_kr_titles
    from src.crawling.theme_cluster import build_theme_clusters, THRESHOLD_CHANGE

    df = cast(pd.DataFrame, fdr.StockListing("KRX"))
    df = cast(pd.DataFrame, df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy())
    df["ChagesRatio"] = cast(pd.Series, pd.to_numeric(df["ChagesRatio"], errors="coerce")).fillna(0)
    df["Amount"] = cast(pd.Series, pd.to_numeric(df["Amount"], errors="coerce")).fillna(0)

    tickers = df["Code"].astype(str).str.zfill(6).tolist()
    sm = SectorMapKR("sector_map_kr.json")
    sector_map = sm.classify(tickers)

    tc_df = pd.DataFrame({
        "ticker": tickers,
        "name": df["Name"].tolist(),
        "change": df["ChagesRatio"].tolist(),
        "amount": df["Amount"].tolist(),
    })

    # 뉴스는 임계값 이상 종목만 (네트워크 최소화, 최대 50종목)
    threshold_tickers = (
        tc_df[tc_df["change"].abs() >= THRESHOLD_CHANGE]["ticker"]
        .head(50)
        .tolist()
    )
    news_titles_by_ticker: dict[str, list[str]] = {}
    for t in threshold_tickers:
        titles = fetch_kr_titles([t])
        if titles:
            news_titles_by_ticker[t] = titles

    return build_theme_clusters(
        tc_df,
        sector_map=sector_map,
        news_titles_by_ticker=news_titles_by_ticker,
    )


def _read_weekly_clusters(mf_sheet: object, iso_week: str) -> list[dict]:
    """
    테마클러스터_일별 탭에서 iso_week 주차에 해당하는 행을 읽어
    aggregate_weekly 가 소비할 cluster dict 리스트로 변환.
    탭이 없거나 데이터가 없으면 빈 리스트 반환.
    """
    from src.crawling.daily_trend_writer import THEME_CLUSTER_TAB, THEME_CLUSTER_HEADERS
    import datetime as _dt
    try:
        sh = mf_sheet.open_or_create()  # type: ignore[attr-defined]
        import gspread
        try:
            ws = sh.worksheet(THEME_CLUSTER_TAB)
        except gspread.WorksheetNotFound:
            return []
        values = ws.get_all_values()
    except Exception:
        return []

    try:
        year_s, week_s = iso_week.split("-W")
        monday = _dt.date.fromisocalendar(int(year_s), int(week_s), 1)
        friday = monday + _dt.timedelta(days=4)  # 월~금 영업일만 집계 (주말 행 제외)
    except Exception:
        return []

    clusters: list[dict] = []
    for row in values[1:]:
        if len(row) < 6 or not row[0]:
            continue
        try:
            row_date = _dt.date.fromisoformat(row[0])
        except ValueError:
            continue
        if not (monday <= row_date <= friday):
            continue
        kw_raw = row[9] if len(row) > 9 else ""
        kw_list: list[tuple[str, int]] = []
        for part in kw_raw.split(","):
            part = part.strip()
            if "(" in part and part.endswith(")"):
                tok, cnt_s = part[:-1].rsplit("(", 1)
                try:
                    kw_list.append((tok.strip(), int(cnt_s)))
                except ValueError:
                    pass
        clusters.append({
            "sector": row[2],
            "avg_change": float(row[5]) if row[5] else 0.0,
            "ticker_count": int(row[3]) if row[3].isdigit() else 0,
            "representatives": [r.strip() for r in row[4].split(",") if r.strip()],
            "keywords_top5": kw_list,
        })
    return clusters


def _production_market_flow_factory(year: int) -> object:
    """시장흐름_{YYYY} 스프레드시트 클라이언트 생성."""
    from src.crawling.daily_trend_writer import MarketFlowSheet, make_sheet_client

    gc = make_sheet_client()
    return MarketFlowSheet(gc, year)


def _number_from(record: dict, *keys: str) -> float:
    """record에서 첫 유효 숫자 값을 읽는다."""
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if num == num:
            return num
    return 0.0


def _build_ohlcv_rows(
    kr_snap: dict | None,
    us_snap: dict | None,
    date_str: str,
) -> list[tuple]:
    """KR/US 스냅샷 universe를 daily_ohlcv upsert row로 변환."""
    rows: list[tuple] = []

    if kr_snap is not None:
        df = kr_snap.get("ohlcv_rows")
        if df is None:
            df = kr_snap.get("top_gainers")
        if df is not None and not getattr(df, "empty", True):
            for record in df.to_dict("records"):
                ticker_raw = str(record.get("Code", record.get("code", ""))).strip()
                if not ticker_raw:
                    continue
                rows.append((
                    ticker_raw.zfill(6),
                    date_str,
                    _number_from(record, "Open", "open"),
                    _number_from(record, "High", "high"),
                    _number_from(record, "Low", "low"),
                    _number_from(record, "Close", "close"),
                    _number_from(record, "Volume", "volume"),
                    _number_from(record, "Amount", "amount"),
                ))

    if us_snap is not None:
        df = us_snap.get("ohlcv_rows")
        if df is None:
            df = us_snap.get("top_gainers")
        if df is not None and not getattr(df, "empty", True):
            for record in df.to_dict("records"):
                ticker_raw = str(record.get("Ticker", record.get("ticker", ""))).strip()
                if not ticker_raw:
                    continue
                rows.append((
                    ticker_raw.upper(),
                    date_str,
                    0.0,
                    _number_from(record, "High", "high"),
                    _number_from(record, "Low", "low"),
                    _number_from(record, "Close", "close"),
                    _number_from(record, "Volume", "volume"),
                    _number_from(record, "Volume.Traded", "volume_value"),
                ))

    return rows


def _production_ohlcv_sink(
    kr_snap: dict | None,
    us_snap: dict | None,
    date_str: str,
) -> None:
    """KR/US 스냅샷 universe의 거래량/거래대금을 SQLite OHLCV 저장소에 upsert."""
    from src.crawling.ohlcv_store import OHLCVStore

    store = OHLCVStore("data/ohlcv.db")
    try:
        rows = _build_ohlcv_rows(kr_snap, us_snap, date_str)
        if rows:
            store.upsert_many(rows)

        store.check_size_warning()
    finally:
        store.close()


def _production_early_signal_source(
    kr_snap: dict | None,
    date_str: str,
) -> list:
    """
    KRX 전종목 중 configured RVOL/change + (streak or 52주고가 근처) 종목 감지.

    OHLCVStore 에서 20일 평균 거래량을 조회하여 RVOL 계산.
    streak_indicators.compute_indicators 로 streak/52주고가비율 계산.
    """
    import pandas as pd
    import importlib
    from typing import cast
    fdr = importlib.import_module("FinanceDataReader")
    from src.crawling.ohlcv_store import OHLCVStore
    from src.crawling.rvol_computer import compute_rvol
    from src.crawling.early_signal import has_early_signal_momentum, is_early_signal
    from src.crawling.streak_indicators import compute_indicators

    if kr_snap is None:
        return []

    df = cast(pd.DataFrame, fdr.StockListing("KRX"))
    df = cast(pd.DataFrame, df[df["Market"].isin(["KOSPI", "KOSDAQ"])].copy())
    df["ChagesRatio"] = cast(pd.Series, pd.to_numeric(df["ChagesRatio"], errors="coerce")).fillna(0)
    df["Amount"] = cast(pd.Series, pd.to_numeric(df["Amount"], errors="coerce")).fillna(0)
    df["Volume"] = pd.to_numeric(df.get("Volume", pd.Series(0, index=df.index)),
                                  errors="coerce").fillna(0)

    store = OHLCVStore("data/ohlcv.db")
    signals: list[dict] = []
    try:
        for _, row in df.iterrows():
            ticker = str(row.get("Code", "")).zfill(6)
            change = float(row.get("ChagesRatio", 0))
            today_vol = float(row.get("Volume", 0))
            rvol = compute_rvol(today_vol, store.avg_volume(ticker, 20))
            if not has_early_signal_momentum(change, rvol):
                continue
            # streak / 52주고가비율 계산 (FDR DataReader 개별 호출)
            try:
                df_detail = fdr.DataReader(ticker, start=None)
                if df_detail is None or len(df_detail) < 20:
                    continue
                ind = compute_indicators(df_detail)
            except Exception:
                continue
            close_price = float(row.get("Close", 0)) or float(row.get("close", 0))
            # compute_indicators returns is_52w_high (bool), not high_52w price.
            # Derive the actual 52-week high directly from the OHLCV DataFrame.
            if "High" in df_detail.columns and len(df_detail) > 0:
                high_52w = float(df_detail["High"].tail(252).max())
            else:
                high_52w = 0.0
            close_ratio = close_price / high_52w if high_52w > 0 else 0.0
            if not is_early_signal(
                change=change,
                rvol=rvol,
                streak=int(ind.get("streak_days", 0)),
                close_ratio_52w=close_ratio,
            ):
                continue
            signals.append({
                "ticker": ticker,
                "name": str(row.get("Name", "")),
                "change": change,
                "rvol": rvol,
                "streak": int(ind.get("streak_days", 0)),
                "close_ratio_52w": close_ratio,
                "amount": float(row.get("Amount", 0)),
            })
    finally:
        store.close()

    return signals


def _production_flow_signal_source(
    kr_snap: dict | None,
    date_str: str,
) -> list:
    """
    KR 급등주 상위 30종목의 외국인/기관 수급 전환 감지.

    flow_fetcher.fetch_flow 로 종목별 이력 수집 후
    flow_signal.detect_reversal 로 전환 판정.
    """
    import FinanceDataReader as fdr
    from src.crawling.flow_fetcher import fetch_flow
    from src.crawling.flow_signal import detect_reversal

    if kr_snap is None:
        return []

    tg = kr_snap.get("top_gainers")
    if tg is None or getattr(tg, "empty", True):
        return []

    tickers = [str(c).zfill(6) for c in tg["Code"].head(30).tolist()]
    names = {str(r["Code"]).zfill(6): str(r.get("Name", "")) for _, r in tg.iterrows()}

    all_signals: list[dict] = []
    for ticker in tickers:
        records = fetch_flow(ticker)
        raw_signals = detect_reversal(records, lookback=5)
        for sig in raw_signals:
            prev = records[1:6]
            sig["ticker"] = ticker
            sig["name"] = names.get(ticker, "")
            sig["prev_days_foreign"] = [r.get("foreign", 0) for r in prev]
            sig["prev_days_institution"] = [r.get("institution", 0) for r in prev]
            all_signals.append(sig)

    return all_signals


def _production_notifier(
    kr_snap: dict | None,
    clusters: list,
    early_signals: list,
    flow_signals: list,
    rc: int,
) -> None:
    """
    Telegram 알림 전송.
    - KR 급등주 >= 5건 → 요약 메시지
    - 강한 테마클러스터(★★★★☆ 이상) → 클러스터별 메시지
    - 파이프라인 오류(rc != 0) → 에러 메시지
    """
    import datetime as _dt
    from src.crawling.telegram_notifier import (
        TelegramNotifier,
        load_telegram_config,
        should_notify_kr_surge,
        should_notify_theme_cluster,
        format_surge_message,
        format_theme_message,
        format_error_message,
    )

    token, chat_id = load_telegram_config(".env.local")
    if not token or not chat_id:
        print("[generate_snapshots] Telegram 토큰/채팅ID 미설정 — 알림 생략")
        return

    _notifier = TelegramNotifier(token=token, chat_id=chat_id)
    date_str = _dt.datetime.now().strftime("%Y-%m-%d")

    if kr_snap is not None:
        surge_count = int(kr_snap.get("surge15_count", 0))
        if should_notify_kr_surge(surge_count):
            tg = kr_snap.get("top_gainers")
            top_tickers: list[str] = []
            if tg is not None and not getattr(tg, "empty", True):
                top_tickers = [str(c) for c in tg["Code"].head(5).tolist()]
            _notifier.send_message(
                format_surge_message(date=date_str, surge_count=surge_count,
                                     top_tickers=top_tickers)
            )

    if should_notify_theme_cluster(clusters):
        _STRONG = {"★★★★☆", "★★★★★"}
        for cluster in clusters:
            if cluster.get("intensity_stars") in _STRONG:
                _notifier.send_message(
                    format_theme_message(date=date_str, cluster=cluster)
                )

    if rc != 0:
        _notifier.send_message(
            format_error_message(
                context="generate_snapshots",
                error=f"파이프라인 일부 실패 (rc={rc})",
            )
        )


def main() -> int:
    return run_snapshots(
        kr_source=_production_kr_source,
        us_source=_production_us_source,
        sheet_factory=_production_sheet_factory,
        news_source=_production_news_source,
        theme_source=_production_theme_source,
        market_flow_factory=_production_market_flow_factory,
        weekly_trend_factory=_production_market_flow_factory,
        ohlcv_sink=_production_ohlcv_sink,
        early_signal_source=_production_early_signal_source,
        flow_signal_source=_production_flow_signal_source,
        notifier=_production_notifier,
    )


if __name__ == "__main__":
    sys.exit(main())
