"""
Daily market trend snapshot → row serializer for Google Sheets.

Converts KR/US trend snapshot dicts (as produced by
test_market_trend.kr_trend_snapshot / us_trend_snapshot) into flat rows
ready for `ws.append_row(...)`.

Design
------
* Row serialization is a **pure function** of the snapshot dict, so it is
  unit-testable without gspread. See test_daily_trend_writer.py.
* Sheet I/O lives in the DailyTrendSheetClient class below and is exercised
  only by the end-to-end runner, not by this unit test.

Target workbook
---------------
One spreadsheet per year: ``시장트렌드_{YYYY}``, with two tabs:
  * ``KR_일별`` — one row per trading day, KR_HEADERS schema
  * ``US_일별`` — one row per trading day, US_HEADERS schema

Dedup key for both tabs is the first column (date). A new snapshot for a
date that already has a row is ignored by the writer.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.crawling.service_account_path import resolve_service_account_file

NEWS_TAB = "뉴스요약"
NEWS_HEADERS: list[str] = [
    "날짜",
    "KR_키워드",
    "US_키워드",
    "AI_요약",
]

KR_HEADERS: list[str] = [
    "날짜",
    "총종목",
    "상승",
    "하락",
    "보합",
    "전체_breadth(%)",
    "KOSPI_breadth(%)",
    "KOSDAQ_breadth(%)",
    "시총가중변동(%)",
    "TOP20_거래대금비중(%)",
    "급등15_개수",
    "급락15_개수",
    "상한가",
    "하한가",
    "최대상승종목",
    "최대상승률(%)",
    "최대하락종목",
    "최대하락률(%)",
    "최대거래대금종목",
    "최대거래대금(억원)",
]

US_HEADERS: list[str] = [
    "date",
    "total",
    "up",
    "down",
    "flat",
    "breadth(%)",
    "cap_weighted(%)",
    "surge8_count",
    "drop8_count",
    "top_gainer",
    "top_gainer(%)",
    "top_loser",
    "top_loser(%)",
    "top_volume",
    "top_volume($B)",
    "sector_leader",
    "sector_leader_avg(%)",
    "sector_laggard",
    "sector_laggard_avg(%)",
]


def format_keywords(kw: list[tuple[str, int]]) -> str:
    """Return 'token1(12), token2(8), ...' or '' for an empty list."""
    if not kw:
        return ""
    return ", ".join(f"{token}({count})" for token, count in kw)


def _pct(ratio: Any) -> float:
    return round(float(ratio) * 100, 2)


def _round2(v: Any) -> float:
    return round(float(v), 2)


def _first(df: pd.DataFrame | None, col: str, default: Any = "") -> Any:
    if df is None or df.empty or col not in df.columns:
        return default
    return df.iloc[0][col]


def kr_snapshot_to_row(snap: dict) -> list:
    """Serialize a KR trend snapshot dict into a row matching KR_HEADERS."""
    tg = snap.get("top_gainers")
    tl = snap.get("top_losers")
    tv = snap.get("top_volume")

    top_gainer_name = str(_first(tg, "Name", ""))
    top_gainer_pct = _round2(_first(tg, "ChagesRatio", 0.0))
    top_loser_name = str(_first(tl, "Name", ""))
    top_loser_pct = _round2(_first(tl, "ChagesRatio", 0.0))
    top_vol_name = str(_first(tv, "Name", ""))
    top_vol_amt = round(float(_first(tv, "Amount", 0.0)) / 1e8, 2)

    return [
        snap["date"],
        int(snap["total"]),
        int(snap["up"]),
        int(snap["down"]),
        int(snap["flat"]),
        _pct(snap["breadth"]),
        _pct(snap["kospi_breadth"]),
        _pct(snap["kosdaq_breadth"]),
        _round2(snap["cap_weighted_change"]),
        _pct(snap["top20_volume_concentration"]),
        int(snap["surge15_count"]),
        int(snap["drop15_count"]),
        int(snap["limit_up"]),
        int(snap["limit_down"]),
        top_gainer_name,
        top_gainer_pct,
        top_loser_name,
        top_loser_pct,
        top_vol_name,
        top_vol_amt,
    ]


def us_snapshot_to_row(snap: dict) -> list:
    """Serialize a US trend snapshot dict into a row matching US_HEADERS."""
    tg = snap.get("top_gainers")
    tl = snap.get("top_losers")
    tv = snap.get("top_volume")
    sectors = snap.get("sectors")

    top_gainer_tk = str(_first(tg, "ticker", ""))
    top_gainer_pct = _round2(_first(tg, "change", 0.0))
    top_loser_tk = str(_first(tl, "ticker", ""))
    top_loser_pct = _round2(_first(tl, "change", 0.0))
    top_vol_tk = str(_first(tv, "ticker", ""))
    top_vol_bn = round(float(_first(tv, "volume_value", 0.0)) / 1e9, 2)

    if sectors is not None and not sectors.empty:
        sector_leader = str(sectors.index[0])
        sector_leader_pct = _round2(sectors.iloc[0]["avg_change"])
        sector_laggard = str(sectors.index[-1])
        sector_laggard_pct = _round2(sectors.iloc[-1]["avg_change"])
    else:
        sector_leader = ""
        sector_leader_pct = 0.0
        sector_laggard = ""
        sector_laggard_pct = 0.0

    return [
        snap["date"],
        int(snap["total"]),
        int(snap["up"]),
        int(snap["down"]),
        int(snap["flat"]),
        _pct(snap["breadth"]),
        _round2(snap["cap_weighted_change"]),
        int(snap["surge8_count"]),
        int(snap["drop8_count"]),
        top_gainer_tk,
        top_gainer_pct,
        top_loser_tk,
        top_loser_pct,
        top_vol_tk,
        top_vol_bn,
        sector_leader,
        sector_leader_pct,
        sector_laggard,
        sector_laggard_pct,
    ]


# ---------------------------------------------------------------------------
# Google Sheets I/O layer
# ---------------------------------------------------------------------------

KR_TAB = "KR_일별"
US_TAB = "US_일별"
_WS_ROWS = "1000"


class DailyTrendSheet:
    """
    Manages the yearly ``시장트렌드_{YYYY}`` spreadsheet.

    The constructor accepts a duck-typed gspread client (supports
    ``open(title)`` and ``create(title)``), so tests can inject a fake
    without touching the network. Callers should pass a real
    ``gspread.Client`` in production.
    """

    def __init__(self, gc: Any, year: int) -> None:
        self._gc = gc
        self._year = int(year)
        self._sh: Any = None

    @property
    def title(self) -> str:
        return f"시장트렌드_{self._year}"

    def open_or_create(self) -> Any:
        """Open the workbook, creating it on first use. Cached after first call."""
        if self._sh is not None:
            return self._sh
        import importlib
        gspread = importlib.import_module("gspread")
        try:
            self._sh = self._gc.open(self.title)
        except gspread.SpreadsheetNotFound:
            self._sh = self._gc.create(self.title)
        return self._sh

    def _ensure_worksheet(self, title: str, headers: list[str]) -> Any:
        import importlib
        gspread = importlib.import_module("gspread")
        sh = self.open_or_create()
        try:
            return sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=title, rows=_WS_ROWS, cols=len(headers))
            ws.append_row(headers, value_input_option="USER_ENTERED")
            return ws

    @staticmethod
    def _existing_dates(ws: Any) -> set[str]:
        values = ws.get_all_values()
        return {row[0] for row in values[1:] if row and row[0]}

    def append_kr_snapshot(self, snap: dict) -> bool:
        """Append a KR snapshot row. Returns False if the date is already present."""
        ws = self._ensure_worksheet(KR_TAB, KR_HEADERS)
        if snap["date"] in self._existing_dates(ws):
            return False
        ws.append_row(kr_snapshot_to_row(snap), value_input_option="USER_ENTERED")
        return True

    def append_us_snapshot(self, snap: dict) -> bool:
        """Append a US snapshot row. Returns False if the date is already present."""
        ws = self._ensure_worksheet(US_TAB, US_HEADERS)
        if snap["date"] in self._existing_dates(ws):
            return False
        ws.append_row(us_snapshot_to_row(snap), value_input_option="USER_ENTERED")
        return True

    def append_news_row(
        self,
        date: str,
        kr_keywords: list[tuple[str, int]],
        us_keywords: list[tuple[str, int]],
        narrative: str,
    ) -> bool:
        """Append a news summary row to the 뉴스요약 tab. Returns False if
        the date is already present."""
        ws = self._ensure_worksheet(NEWS_TAB, NEWS_HEADERS)
        if date in self._existing_dates(ws):
            return False
        ws.append_row(
            [date, format_keywords(kr_keywords), format_keywords(us_keywords), narrative],
            value_input_option="USER_ENTERED",
        )
        return True


def make_sheet_client(service_account_file: str | None = None) -> Any:
    """Return an authorized gspread client using the repo service account."""
    import importlib
    gspread = importlib.import_module("gspread")
    Credentials = importlib.import_module("google.oauth2.service_account").Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(resolve_service_account_file(service_account_file), scopes=scopes)
    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# 시장흐름_{YYYY} — 테마 클러스터 시트
# ---------------------------------------------------------------------------

THEME_CLUSTER_TAB = "테마클러스터_일별"
THEME_CLUSTER_HEADERS: list[str] = [
    "날짜",
    "방향",
    "섹터",
    "포함종목수",
    "대표종목(3개)",
    "평균등락률(%)",
    "최대등락률(%)",
    "테마강도",
    "합산거래대금(억)",
    "관련뉴스키워드(Top5)",
]


class MarketFlowSheet:
    """
    ``시장흐름_{YYYY}`` 스프레드시트 관리 클래스.

    ``DailyTrendSheet`` (시장트렌드_YYYY) 와 별개의 스프레드시트이므로
    신규 클래스로 분리한다 (Option A — 하네스 권장).

    생성자에 duck-typed gspread 클라이언트를 주입받으므로
    단위 테스트에서 네트워크 없이 FakeGspreadClient 로 교체 가능.
    """

    def __init__(self, gc: Any, year: int) -> None:
        self._gc = gc
        self._year = int(year)
        self._sh: Any = None

    @property
    def title(self) -> str:
        return f"시장흐름_{self._year}"

    def open_or_create(self) -> Any:
        """워크북을 열거나 없으면 생성. 첫 호출 이후 캐시."""
        if self._sh is not None:
            return self._sh
        import importlib
        gspread = importlib.import_module("gspread")
        try:
            self._sh = self._gc.open(self.title)
        except gspread.SpreadsheetNotFound:
            self._sh = self._gc.create(self.title)
        return self._sh

    def _ensure_worksheet(self, title: str, headers: list[str]) -> Any:
        import importlib
        gspread = importlib.import_module("gspread")
        sh = self.open_or_create()
        try:
            return sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=title, rows="1000", cols=len(headers))
            ws.append_row(headers, value_input_option="USER_ENTERED")
            return ws

    @staticmethod
    def _existing_keys(ws: Any) -> set[tuple[str, str, str]]:
        """(날짜, 방향, 섹터) 튜플 집합 반환 — dedup 용."""
        values = ws.get_all_values()
        keys: set[tuple[str, str, str]] = set()
        for row in values[1:]:
            if row and len(row) >= 3 and row[0]:
                keys.add((str(row[0]), str(row[1]), str(row[2])))
        return keys

    def append_theme_clusters(
        self,
        date: str,
        clusters: list[dict],
    ) -> int:
        """
        클러스터 리스트를 테마클러스터_일별 탭에 append.

        dedup key: (날짜, 방향, 섹터) — 이미 존재하는 행은 스킵.

        Parameters
        ----------
        date : str
            날짜 문자열 (예: "2026-04-16").
        clusters : list[dict]
            theme_cluster.build_theme_clusters() 반환값.

        Returns
        -------
        int — 실제로 기록된 행 수.
        """
        from src.crawling.theme_cluster import cluster_to_sheet_row
        ws = self._ensure_worksheet(THEME_CLUSTER_TAB, THEME_CLUSTER_HEADERS)
        existing = self._existing_keys(ws)
        appended = 0
        for cluster in clusters:
            key = (date, str(cluster["direction"]), str(cluster["sector"]))
            if key in existing:
                continue
            row = cluster_to_sheet_row(date, cluster)
            ws.append_row(row, value_input_option="USER_ENTERED")
            existing.add(key)
            appended += 1
        return appended

    def get_prev_week_frequencies(self, iso_week: str) -> dict[str, int]:
        """
        테마트렌드_주간 탭에서 직전 주차의 {섹터: 출현빈도} dict 반환.
        탭이 없거나 직전 주 데이터가 없으면 빈 dict 반환.
        """
        try:
            ws = self._ensure_worksheet(THEME_TREND_TAB, THEME_TREND_HEADERS)
            values = ws.get_all_values()
        except Exception:
            return {}

        try:
            import datetime as _dt
            year_s, week_s = iso_week.split("-W")
            ref = _dt.date.fromisocalendar(int(year_s), int(week_s), 1)
            prev = ref - _dt.timedelta(weeks=1)
            prev_cal = prev.isocalendar()
            prev_iso = f"{prev_cal[0]}-W{prev_cal[1]:02d}"
        except Exception:
            return {}

        freq: dict[str, int] = {}
        for row in values[1:]:
            if len(row) >= 3 and row[0] == prev_iso:
                sector = str(row[1]).strip()
                try:
                    freq[sector] = int(row[2])
                except (ValueError, IndexError):
                    pass
        return freq

    def append_weekly_trends(
        self,
        iso_week: str,
        daily_clusters: list[dict],
    ) -> int:
        """
        일별 클러스터 리스트를 집계하여 테마트렌드_주간 탭에 append.

        dedup key: (주차(ISO), 섹터) — 이미 존재하는 행은 스킵.
        직전 주 빈도는 get_prev_week_frequencies 로 조회.

        Returns
        -------
        int — 실제로 기록된 행 수.
        """
        from src.crawling.theme_trend import aggregate_weekly, weekly_trend_to_sheet_row

        ws = self._ensure_worksheet(THEME_TREND_TAB, THEME_TREND_HEADERS)

        existing_values = ws.get_all_values()
        existing: set[tuple[str, str]] = set()
        for row in existing_values[1:]:
            if len(row) >= 2 and row[0]:
                existing.add((str(row[0]), str(row[1])))

        prev_freq = self.get_prev_week_frequencies(iso_week)
        weekly_rows = aggregate_weekly(daily_clusters, prev_freq)

        appended = 0
        for wr in weekly_rows:
            key = (iso_week, wr["sector"])
            if key in existing:
                continue
            sheet_row = weekly_trend_to_sheet_row(iso_week, wr)
            ws.append_row(sheet_row, value_input_option="USER_ENTERED")
            existing.add(key)
            appended += 1
        return appended

    def append_early_signals(
        self,
        date: str,
        signals: list[dict],
    ) -> int:
        """
        조기신호 리스트를 조기신호_관찰 탭에 append.

        dedup key: (날짜, 종목코드) — 이미 존재하는 행은 스킵.

        Parameters
        ----------
        date    : "YYYY-MM-DD" 형식 날짜
        signals : early_signal.build_early_signal_row 반환값의 dict 리스트.
                  각 dict: {ticker, name, change, rvol, streak,
                            close_ratio_52w, amount}

        Returns
        -------
        int — 실제로 기록된 행 수.
        """
        from src.crawling.early_signal import (
            EARLY_SIGNAL_HEADERS as _HEADERS,
            build_early_signal_row,
        )

        ws = self._ensure_worksheet(EARLY_SIGNAL_TAB, EARLY_SIGNAL_HEADERS)
        values = ws.get_all_values()
        existing: set[tuple[str, str]] = set()
        for row in values[1:]:
            if len(row) >= 2 and row[0]:
                existing.add((str(row[0]), str(row[1])))

        appended = 0
        for sig in signals:
            ticker = str(sig.get("ticker", ""))
            key = (date, ticker)
            if key in existing:
                continue
            row = build_early_signal_row(
                date=date,
                ticker=ticker,
                name=str(sig.get("name", "")),
                change=float(sig.get("change", 0)),
                rvol=float(sig.get("rvol", 0)),
                streak=int(sig.get("streak", 0)),
                close_ratio_52w=float(sig.get("close_ratio_52w", 0)),
                amount=float(sig.get("amount", 0)),
            )
            ws.append_row(row, value_input_option="USER_ENTERED")
            existing.add(key)
            appended += 1
        return appended

    def update_5day_return(
        self,
        date: str,
        ticker: str,
        return_pct: float,
    ) -> bool:
        """
        조기신호_관찰 탭에서 (date, ticker) 행의 5일후수익률(%) 컬럼을 업데이트.

        Returns True if the row was found and updated, False otherwise.
        """
        ws = self._ensure_worksheet(EARLY_SIGNAL_TAB, EARLY_SIGNAL_HEADERS)
        values = ws.get_all_values()
        # 헤더 포함이므로 row index = 1-based sheet row
        for i, row in enumerate(values[1:], start=2):
            if len(row) >= 2 and row[0] == date and row[1] == ticker:
                # 5일후수익률은 마지막 컬럼 (index 8, 1-based col 9)
                col_idx = len(EARLY_SIGNAL_HEADERS)
                ws.update_cell(i, col_idx, round(float(return_pct), 2))
                return True
        return False

    def append_flow_signals(
        self,
        date: str,
        signals: list[dict],
    ) -> int:
        """
        수급 전환 시그널 리스트를 수급전환_포착 탭에 append.

        dedup key: (날짜, 종목코드, 전환유형).

        Parameters
        ----------
        date    : "YYYY-MM-DD" 형식 날짜
        signals : flow_signal.detect_reversal 반환 dict 에
                  ticker, name 이 추가된 형태.
                  keys: ticker, name, reversal_type, today_foreign,
                        today_institution, prev_days_foreign, prev_days_institution

        Returns
        -------
        int — 실제로 기록된 행 수.
        """
        from src.crawling.flow_signal import build_flow_signal_row

        ws = self._ensure_worksheet(FLOW_SIGNAL_TAB, FLOW_SIGNAL_HEADERS)
        values = ws.get_all_values()
        existing: set[tuple[str, str, str]] = set()
        for row in values[1:]:
            if len(row) >= 4 and row[0]:
                existing.add((str(row[0]), str(row[1]), str(row[3])))

        appended = 0
        for sig in signals:
            ticker = str(sig.get("ticker", ""))
            reversal_type = str(sig.get("reversal_type", ""))
            key = (date, ticker, reversal_type)
            if key in existing:
                continue
            row = build_flow_signal_row(
                date=date,
                ticker=ticker,
                name=str(sig.get("name", "")),
                reversal_type=reversal_type,
                today_foreign=int(sig.get("today_foreign", 0)),
                today_institution=int(sig.get("today_institution", 0)),
                prev_days_foreign=list(sig.get("prev_days_foreign", [])),
                prev_days_institution=list(sig.get("prev_days_institution", [])),
            )
            ws.append_row(row, value_input_option="USER_ENTERED")
            existing.add(key)
            appended += 1
        return appended


# ---------------------------------------------------------------------------
# 테마트렌드 주간 시트 상수
# ---------------------------------------------------------------------------

THEME_TREND_TAB = "테마트렌드_주간"
THEME_TREND_HEADERS: list[str] = [
    "주차(ISO)",
    "섹터",
    "출현빈도",
    "WoW변화",
    "주간누적평균등락률(%)",
    "대표종목",
    "주요뉴스키워드(Top5)",
]

# ---------------------------------------------------------------------------
# 이슈 #7: 조기신호_관찰 탭 상수
# ---------------------------------------------------------------------------

EARLY_SIGNAL_TAB = "조기신호_관찰"
EARLY_SIGNAL_HEADERS: list[str] = [
    "날짜",
    "종목코드",
    "종목명",
    "등락률(%)",
    "RVOL",
    "연속봉",
    "52주고가비율",
    "합산거래대금(억)",
    "5일후수익률(%)",
]

# ---------------------------------------------------------------------------
# 이슈 #11: 수급전환_포착 탭 상수
# ---------------------------------------------------------------------------

FLOW_SIGNAL_TAB = "수급전환_포착"
FLOW_SIGNAL_HEADERS: list[str] = [
    "날짜",
    "종목코드",
    "종목명",
    "전환유형",
    "당일외국인순매매",
    "당일기관순매매",
    "직전5일외국인누적",
    "직전5일기관누적",
]
