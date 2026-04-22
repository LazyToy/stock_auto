"""
MarketFlowSheet 단위 테스트.

daily_trend_writer.MarketFlowSheet 의 순수 로직(시트 I/O 제외)과
gspread fake 를 통한 append_theme_clusters 동작을 검증한다.
네트워크/실제 Google Sheets 호출 없음.

실행:
    python tests/py/test_daily_trend_writer_theme.py
"""
from __future__ import annotations
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 daily_trend_writer 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Any


# ---------------------------------------------------------------------------
# gspread 인메모리 Fake (기존 test_daily_trend_sheet.py 패턴 차용)
# ---------------------------------------------------------------------------

class FakeWorksheet:
    """append_row / get_all_values 만 지원하는 인메모리 시트."""

    def __init__(self, title: str, headers: list[str]) -> None:
        self.title = title
        self._rows: list[list] = [headers[:]] if headers else []

    def append_row(self, row: list, value_input_option: str = "RAW") -> None:
        self._rows.append(row[:])

    def get_all_values(self) -> list[list]:
        return [r[:] for r in self._rows]


class FakeSpreadsheet:
    def __init__(self) -> None:
        self._worksheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, title: str) -> FakeWorksheet:
        import gspread  # type: ignore
        if title not in self._worksheets:
            raise gspread.WorksheetNotFound(title)
        return self._worksheets[title]

    def add_worksheet(self, title: str, rows: Any, cols: Any) -> FakeWorksheet:
        ws = FakeWorksheet(title, [])
        self._worksheets[title] = ws
        return ws


class FakeGspreadClient:
    def __init__(self) -> None:
        self._sheets: dict[str, FakeSpreadsheet] = {}

    def open(self, title: str) -> FakeSpreadsheet:
        import gspread  # type: ignore
        if title not in self._sheets:
            raise gspread.SpreadsheetNotFound(title)
        return self._sheets[title]

    def create(self, title: str) -> FakeSpreadsheet:
        sh = FakeSpreadsheet()
        self._sheets[title] = sh
        return sh


# ---------------------------------------------------------------------------
# 샘플 클러스터
# ---------------------------------------------------------------------------

def _make_cluster(direction: str = "up", sector: str = "2차전지") -> dict:
    return {
        "direction": direction,
        "sector": sector,
        "ticker_count": 3,
        "representatives": ["A", "B", "C"],
        "avg_change": 7.0 if direction == "up" else -6.5,
        "max_change": 8.0 if direction == "up" else -7.0,
        "intensity_stars": "★★★★☆",
        "total_amount_100m": 450.0,
        "keywords_top5": [("리튬", 3)],
    }


# ---------------------------------------------------------------------------
# MarketFlowSheet.title
# ---------------------------------------------------------------------------

def test_market_flow_sheet_title():
    """시장흐름_{YYYY} 타이틀 형식 검증."""
    from daily_trend_writer import MarketFlowSheet
    gc = FakeGspreadClient()
    sheet = MarketFlowSheet(gc, 2026)
    assert sheet.title == "시장흐름_2026"


# ---------------------------------------------------------------------------
# append_theme_clusters — 최초 기록
# ---------------------------------------------------------------------------

def test_append_theme_clusters_creates_tab_and_writes():
    """테마클러스터_일별 탭이 없으면 생성 후 헤더+데이터 기록."""
    from daily_trend_writer import MarketFlowSheet, THEME_CLUSTER_HEADERS, THEME_CLUSTER_TAB
    gc = FakeGspreadClient()
    sheet = MarketFlowSheet(gc, 2026)
    count = sheet.append_theme_clusters("2026-04-16", [_make_cluster()])
    assert count == 1

    # 시트 확인
    sh = gc._sheets["시장흐름_2026"]
    ws = sh._worksheets[THEME_CLUSTER_TAB]
    rows = ws.get_all_values()
    assert rows[0] == THEME_CLUSTER_HEADERS   # 헤더 행
    assert rows[1][0] == "2026-04-16"         # 날짜
    assert rows[1][1] == "up"                 # 방향
    assert rows[1][2] == "2차전지"            # 섹터


# ---------------------------------------------------------------------------
# append_theme_clusters — 헤더 순서 검증
# ---------------------------------------------------------------------------

def test_append_theme_clusters_header_order():
    """헤더가 명세 순서와 정확히 일치해야 한다."""
    from daily_trend_writer import THEME_CLUSTER_HEADERS
    expected = [
        "날짜", "방향", "섹터", "포함종목수", "대표종목(3개)",
        "평균등락률(%)", "최대등락률(%)", "테마강도", "합산거래대금(억)", "관련뉴스키워드(Top5)",
    ]
    assert THEME_CLUSTER_HEADERS == expected


# ---------------------------------------------------------------------------
# append_theme_clusters — dedup (같은 날짜+방향+섹터)
# ---------------------------------------------------------------------------

def test_append_theme_clusters_dedup_skips_existing():
    """(date, direction, sector) 가 이미 있으면 스킵, 새 것만 기록."""
    from daily_trend_writer import MarketFlowSheet
    gc = FakeGspreadClient()
    sheet = MarketFlowSheet(gc, 2026)

    # 첫 번째 기록
    sheet.append_theme_clusters("2026-04-16", [_make_cluster("up", "2차전지")])
    # 같은 key 로 재시도 → 스킵
    count = sheet.append_theme_clusters("2026-04-16", [_make_cluster("up", "2차전지")])
    assert count == 0

    sh = gc._sheets["시장흐름_2026"]
    from daily_trend_writer import THEME_CLUSTER_TAB
    rows = sh._worksheets[THEME_CLUSTER_TAB].get_all_values()
    assert len(rows) == 2   # 헤더 + 데이터 1개만


def test_append_theme_clusters_dedup_allows_different_direction():
    """같은 날짜·섹터라도 방향이 다르면 새 행으로 기록한다."""
    from daily_trend_writer import MarketFlowSheet, THEME_CLUSTER_TAB
    gc = FakeGspreadClient()
    sheet = MarketFlowSheet(gc, 2026)

    sheet.append_theme_clusters("2026-04-16", [_make_cluster("up", "2차전지")])
    count = sheet.append_theme_clusters("2026-04-16", [_make_cluster("down", "2차전지")])
    assert count == 1

    sh = gc._sheets["시장흐름_2026"]
    rows = sh._worksheets[THEME_CLUSTER_TAB].get_all_values()
    assert len(rows) == 3   # 헤더 + up행 + down행


# ---------------------------------------------------------------------------
# append_theme_clusters — 빈 클러스터 리스트
# ---------------------------------------------------------------------------

def test_append_theme_clusters_empty_list():
    """클러스터 0개 → 0 반환, 탭은 생성되지만 헤더만 존재."""
    from daily_trend_writer import MarketFlowSheet, THEME_CLUSTER_TAB
    gc = FakeGspreadClient()
    sheet = MarketFlowSheet(gc, 2026)
    count = sheet.append_theme_clusters("2026-04-16", [])
    assert count == 0

    sh = gc._sheets["시장흐름_2026"]
    rows = sh._worksheets[THEME_CLUSTER_TAB].get_all_values()
    assert len(rows) == 1   # 헤더만


# ---------------------------------------------------------------------------
# append_theme_clusters — 복수 클러스터 일괄 기록
# ---------------------------------------------------------------------------

def test_append_theme_clusters_multiple():
    """여러 클러스터를 한 번에 기록한다."""
    from daily_trend_writer import MarketFlowSheet, THEME_CLUSTER_TAB
    gc = FakeGspreadClient()
    sheet = MarketFlowSheet(gc, 2026)
    clusters = [
        _make_cluster("up", "2차전지"),
        _make_cluster("up", "반도체"),
        _make_cluster("down", "바이오"),
    ]
    count = sheet.append_theme_clusters("2026-04-16", clusters)
    assert count == 3

    sh = gc._sheets["시장흐름_2026"]
    rows = sh._worksheets[THEME_CLUSTER_TAB].get_all_values()
    assert len(rows) == 4   # 헤더 + 3개


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_market_flow_sheet_title()
    test_append_theme_clusters_creates_tab_and_writes()
    test_append_theme_clusters_header_order()
    test_append_theme_clusters_dedup_skips_existing()
    test_append_theme_clusters_dedup_allows_different_direction()
    test_append_theme_clusters_empty_list()
    test_append_theme_clusters_multiple()
    print("[PASS] all tests")
