from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from dashboard.components.crawling_results_tab import (
    build_results_count_figure,
    build_theme_heatmap_figure,
    build_theme_timeline_figure,
    filter_results_dataframe,
    filter_result_schemas,
    render_live_sheet_probe_section,
    summarize_results_dataframe,
)
from src.crawling.sheets_reader import LiveSheetBackendStatus, LiveSheetProbeResult
from src.crawling.schemas import get_result_sheet_schema


def test_summarize_results_dataframe_reports_rows_latest_date_and_unique_symbols() -> None:
    df = pd.DataFrame(
        [
            {"날짜": "2026-04-20", "종목코드": "005930", "종목명": "삼성전자"},
            {"날짜": "2026-04-21", "종목코드": "000660", "종목명": "SK하이닉스"},
            {"날짜": "2026-04-21", "종목코드": "005930", "종목명": "삼성전자"},
        ]
    )

    summary = summarize_results_dataframe(df)

    assert summary.row_count == 3
    assert summary.latest_date == "2026-04-21"
    assert summary.unique_symbols == 2


def test_filter_results_dataframe_filters_by_query_and_date_range() -> None:
    df = pd.DataFrame(
        [
            {"날짜": "2026-04-19", "종목명": "삼성전자", "섹터": "반도체"},
            {"날짜": "2026-04-20", "종목명": "현대차", "섹터": "자동차"},
            {"날짜": "2026-04-21", "종목명": "SK하이닉스", "섹터": "반도체"},
        ]
    )

    filtered = filter_results_dataframe(
        df,
        query="반도체",
        date_from="2026-04-20",
        date_to="2026-04-21",
    )

    assert filtered.to_dict("records") == [
        {"날짜": "2026-04-21", "종목명": "SK하이닉스", "섹터": "반도체"}
    ]


def test_filter_results_dataframe_returns_original_columns_for_no_match() -> None:
    df = pd.DataFrame([{"date": "2026-04-21", "ticker": "AAPL"}])

    filtered = filter_results_dataframe(df, query="missing")

    assert list(filtered.columns) == ["date", "ticker"]
    assert filtered.empty


def test_filter_result_schemas_filters_by_market_and_category() -> None:
    schemas = filter_result_schemas(market="KR", category="flow")

    assert [schema.key for schema in schemas] == [
        "flow_theme_clusters",
        "flow_theme_trends",
        "flow_early_signals",
        "flow_reversal_signals",
    ]


def test_build_results_count_figure_uses_plotly_bar_chart() -> None:
    df = pd.DataFrame(
        [
            {"날짜": "2026-04-20", "종목명": "삼성전자"},
            {"날짜": "2026-04-20", "종목명": "SK하이닉스"},
            {"날짜": "2026-04-21", "종목명": "현대차"},
        ]
    )

    fig = build_results_count_figure(df)

    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "bar"
    assert list(fig.data[0].x) == ["2026-04-20", "2026-04-21"]
    assert list(fig.data[0].y) == [2, 1]


def test_build_theme_heatmap_figure_maps_date_sector_cells() -> None:
    df = pd.DataFrame(
        [
            {"날짜": "2026-04-20", "섹터": "반도체", "평균등락률(%)": 5.2},
            {"날짜": "2026-04-21", "섹터": "자동차", "평균등락률(%)": -3.1},
        ]
    )

    fig = build_theme_heatmap_figure(df)

    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "heatmap"
    assert list(fig.data[0].x) == ["2026-04-20", "2026-04-21"]
    assert list(fig.data[0].y) == ["반도체", "자동차"]


def test_build_theme_timeline_figure_groups_weekly_trends_by_sector() -> None:
    df = pd.DataFrame(
        [
            {"주차(ISO)": "2026-W15", "섹터": "반도체", "출현빈도": 3},
            {"주차(ISO)": "2026-W16", "섹터": "반도체", "출현빈도": 5},
            {"주차(ISO)": "2026-W16", "섹터": "자동차", "출현빈도": 2},
        ]
    )

    fig = build_theme_timeline_figure(df)

    assert isinstance(fig, go.Figure)
    assert [trace.name for trace in fig.data] == ["반도체", "자동차"]
    assert list(fig.data[0].x) == ["2026-W15", "2026-W16"]
    assert list(fig.data[0].y) == [3, 5]


def test_dashboard_app_wires_crawling_results_tab() -> None:
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "from dashboard.components.crawling_results_tab import render_crawling_results_tab" in text
    assert "크롤링 결과" in text
    assert "render_crawling_results_tab()" in text


def test_render_live_sheet_probe_section_warns_when_live_probe_is_not_ready() -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.warning_calls = []
            self.button_calls = []

        def warning(self, message):
            self.warning_calls.append(message)

        def button(self, label, **kwargs):
            self.button_calls.append((label, kwargs))
            return False

    fake_st = FakeStreamlit()
    status = LiveSheetBackendStatus(
        service_account_file="missing.json",
        service_account_configured=False,
        configured_spreadsheet_id_envs=(),
        missing_spreadsheet_id_envs=("SHEET_ID_FLOW",),
        live_probe_ready=False,
    )

    render_live_sheet_probe_section(
        schema_key="trend_kr_daily",
        year=2026,
        month="202604",
        backend_status=status,
        st_api=fake_st,
    )

    assert fake_st.warning_calls
    assert "missing.json" in fake_st.warning_calls[0]
    assert fake_st.button_calls == []


def test_render_live_sheet_probe_section_runs_probe_and_reports_success() -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.caption_calls = []
            self.success_calls = []
            self.error_calls = []

        def caption(self, message):
            self.caption_calls.append(message)

        def success(self, message):
            self.success_calls.append(message)

        def error(self, message):
            self.error_calls.append(message)

        def button(self, label, **kwargs):
            return True

    fake_st = FakeStreamlit()
    status = LiveSheetBackendStatus(
        service_account_file="config/google_service_account.json",
        service_account_configured=True,
        configured_spreadsheet_id_envs=("SHEET_ID_TREND",),
        missing_spreadsheet_id_envs=(),
        live_probe_ready=True,
    )

    def fake_probe(schema_key, **kwargs):
        return LiveSheetProbeResult(
            schema_key=schema_key,
            request=kwargs["request"],
            workbook_title="market_trend_2026",
            worksheet_title=get_result_sheet_schema(schema_key).worksheet_title,
            row_count=3,
            spreadsheet_url="https://docs.google.com/spreadsheets/d/live-probe",
            from_cache=False,
        )

    render_live_sheet_probe_section(
        schema_key="trend_kr_daily",
        year=2026,
        month="202604",
        backend_status=status,
        probe_live_sheet=fake_probe,
        st_api=fake_st,
    )

    assert fake_st.error_calls == []
    assert any("3" in message for message in fake_st.success_calls)
    assert "https://docs.google.com/spreadsheets/d/live-probe" in fake_st.caption_calls[-1]
