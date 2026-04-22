from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.crawling.schemas import ResultSheetSchema, get_result_sheet_schema, list_result_sheet_schemas
from src.crawling.sheets_reader import (
    LiveSheetBackendStatus,
    LiveSheetProbeResult,
    SheetReadRequest,
    SheetReadResult,
    describe_live_sheet_backend,
    probe_live_sheet_access,
    read_sheet_dataframe,
)


DATE_COLUMNS = ("날짜", "date", "Date", "주차(ISO)")
SYMBOL_COLUMNS = ("종목코드", "티커", "ticker", "Ticker", "종목명", "종목")
CATEGORY_LABELS = {
    "shadowing": "쉐도잉",
    "trend": "시장트렌드",
    "flow": "시장흐름",
}


@dataclass(frozen=True)
class ResultsSummary:
    row_count: int
    latest_date: str
    unique_symbols: int


def _first_existing_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column
    return None


def summarize_results_dataframe(df: pd.DataFrame) -> ResultsSummary:
    date_column = _first_existing_column(df, DATE_COLUMNS)
    symbol_column = _first_existing_column(df, SYMBOL_COLUMNS)

    latest_date = ""
    if date_column is not None and not df.empty:
        values = df[date_column].dropna().astype(str)
        values = values[values.str.strip() != ""]
        if not values.empty:
            latest_date = str(values.max())

    unique_symbols = 0
    if symbol_column is not None and not df.empty:
        values = df[symbol_column].dropna().astype(str)
        unique_symbols = int(values[values.str.strip() != ""].nunique())

    return ResultsSummary(
        row_count=int(len(df)),
        latest_date=latest_date,
        unique_symbols=unique_symbols,
    )


def filter_results_dataframe(
    df: pd.DataFrame,
    *,
    query: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    filtered = df.copy()
    date_column = _first_existing_column(filtered, DATE_COLUMNS)

    if date_column is not None:
        date_values = filtered[date_column].astype(str)
        if date_from:
            filtered = filtered[date_values >= str(date_from)]
            date_values = filtered[date_column].astype(str)
        if date_to:
            filtered = filtered[date_values <= str(date_to)]

    normalized_query = query.strip().lower()
    if normalized_query:
        row_text = filtered.astype(str).agg(" ".join, axis=1).str.lower()
        filtered = filtered[row_text.str.contains(normalized_query, regex=False)]

    return filtered


def filter_result_schemas(
    *,
    market: str = "전체",
    category: str = "전체",
) -> tuple[ResultSheetSchema, ...]:
    schemas = list_result_sheet_schemas()
    if market != "전체":
        schemas = tuple(
            schema for schema in schemas if schema.market in {market, "ALL"}
        )
    if category != "전체":
        schemas = tuple(schema for schema in schemas if schema.category == category)
    return schemas


def build_results_count_figure(df: pd.DataFrame) -> go.Figure:
    date_column = _first_existing_column(df, DATE_COLUMNS)
    fig = go.Figure()
    if date_column is None or df.empty:
        return fig

    counts = df.groupby(date_column, dropna=False).size().reset_index(name="count")
    counts[date_column] = counts[date_column].astype(str)
    counts = counts.sort_values(date_column)
    fig.add_bar(x=counts[date_column].tolist(), y=counts["count"].tolist(), name="건수")
    fig.update_layout(
        xaxis_title=date_column,
        yaxis_title="건수",
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
    )
    return fig


def _unique_preserve_order(values: pd.Series) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values.dropna().astype(str):
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def build_theme_heatmap_figure(df: pd.DataFrame) -> go.Figure:
    required = {"날짜", "섹터", "평균등락률(%)"}
    fig = go.Figure()
    if df.empty or not required.issubset(df.columns):
        return fig

    dates = sorted(_unique_preserve_order(df["날짜"]))
    sectors = _unique_preserve_order(df["섹터"])
    matrix: list[list[float | None]] = []
    for sector in sectors:
        row: list[float | None] = []
        for date in dates:
            matched = df[(df["날짜"].astype(str) == date) & (df["섹터"].astype(str) == sector)]
            if matched.empty:
                row.append(None)
            else:
                row.append(float(pd.to_numeric(matched["평균등락률(%)"], errors="coerce").iloc[-1]))
        matrix.append(row)

    fig.add_heatmap(
        x=dates,
        y=sectors,
        z=matrix,
        colorscale=[
            [0.0, "#b91c1c"],
            [0.5, "#f8fafc"],
            [1.0, "#15803d"],
        ],
        zmid=0,
        colorbar={"title": "%"},
    )
    fig.update_layout(
        xaxis_title="날짜",
        yaxis_title="섹터",
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
    )
    return fig


def build_theme_timeline_figure(df: pd.DataFrame) -> go.Figure:
    required = {"주차(ISO)", "섹터", "출현빈도"}
    fig = go.Figure()
    if df.empty or not required.issubset(df.columns):
        return fig

    work = df.copy()
    work["주차(ISO)"] = work["주차(ISO)"].astype(str)
    work["출현빈도"] = pd.to_numeric(work["출현빈도"], errors="coerce").fillna(0)
    for sector, group in work.groupby("섹터", sort=False):
        group = group.sort_values("주차(ISO)")
        fig.add_scatter(
            x=group["주차(ISO)"].tolist(),
            y=group["출현빈도"].tolist(),
            mode="lines+markers",
            name=str(sector),
        )
    fig.update_layout(
        xaxis_title="주차",
        yaxis_title="출현빈도",
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
    )
    return fig


def _default_month(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return current.strftime("%Y%m")


def _default_year(now: datetime | None = None) -> int:
    current = now or datetime.now()
    return int(current.year)


@st.cache_data(ttl=300)
def load_crawling_results(schema_key: str, year: int, month: str) -> SheetReadResult:
    schema = get_result_sheet_schema(schema_key)
    request = SheetReadRequest(
        schema=schema,
        year=year if schema.workbook_kind != "monthly" else None,
        month=month if schema.workbook_kind == "monthly" else None,
    )
    return read_sheet_dataframe(request)


def _render_summary(summary: ResultsSummary, *, st_api: Any = st) -> None:
    col1, col2, col3 = st_api.columns(3)
    col1.metric("행 수", summary.row_count)
    col2.metric("최신 날짜", summary.latest_date or "-")
    col3.metric("고유 종목", summary.unique_symbols)


def _render_chart(schema: ResultSheetSchema, df: pd.DataFrame, *, st_api: Any = st) -> None:
    if schema.key == "flow_theme_clusters":
        fig = build_theme_heatmap_figure(df)
    elif schema.key == "flow_theme_trends":
        fig = build_theme_timeline_figure(df)
    else:
        fig = build_results_count_figure(df)
    if fig.data:
        st_api.plotly_chart(fig, use_container_width=True)


def _schema_label(schema: ResultSheetSchema) -> str:
    return schema.label


def render_live_sheet_probe_section(
    *,
    schema_key: str,
    year: int,
    month: str,
    backend_status: LiveSheetBackendStatus | None = None,
    probe_live_sheet: Any = probe_live_sheet_access,
    st_api: Any = st,
) -> None:
    status = backend_status or describe_live_sheet_backend()
    if not status.live_probe_ready:
        st_api.warning(
            f"Live Google Sheets check unavailable: service account file not found at {status.service_account_file}"
        )
        return

    st_api.caption(f"Live Google Sheets check ready: {status.service_account_file}")
    if status.missing_spreadsheet_id_envs:
        st_api.caption(
            "Workbook ID envs not set; live probe will fall back to workbook title lookup: "
            + ", ".join(status.missing_spreadsheet_id_envs)
        )
    if not st_api.button("Live Google Sheets check", key=f"crawling_results_live_probe_{schema_key}"):
        return

    request = SheetReadRequest(
        schema=get_result_sheet_schema(schema_key),
        year=year if get_result_sheet_schema(schema_key).workbook_kind != "monthly" else None,
        month=month if get_result_sheet_schema(schema_key).workbook_kind == "monthly" else None,
    )
    try:
        probe_result: LiveSheetProbeResult = probe_live_sheet(
            schema_key,
            request=request,
            year=year,
            month=month,
        )
    except Exception as exc:
        st_api.error(f"Live Google Sheets check failed: {exc}")
        return

    st_api.success(f"Live Google Sheets check OK: {probe_result.row_count} rows")
    if probe_result.spreadsheet_url:
        st_api.caption(probe_result.spreadsheet_url)


def render_crawling_results_tab() -> None:
    st.header("크롤링 결과 조회")

    market = st.selectbox(
        "시장",
        ["전체", "KR", "US"],
        key="crawling_results_market",
    )
    category_label = st.selectbox(
        "카테고리",
        ["전체", *CATEGORY_LABELS.values()],
        key="crawling_results_category",
    )
    category = next(
        (key for key, label in CATEGORY_LABELS.items() if label == category_label),
        "전체",
    )
    schemas = filter_result_schemas(market=market, category=category)
    if not schemas:
        st.info("선택한 조건에 맞는 조회 대상이 없습니다.")
        return

    schema = st.selectbox(
        "조회 대상",
        schemas,
        format_func=_schema_label,
        key="crawling_results_schema",
    )
    assert isinstance(schema, ResultSheetSchema)

    col1, col2 = st.columns(2)
    year = int(col1.number_input("연도", min_value=2020, max_value=2100, value=_default_year()))
    month = col2.text_input("월", value=_default_month(), max_chars=6)
    query = st.text_input("검색", value="", key="crawling_results_query")
    date_col1, date_col2 = st.columns(2)
    date_from = date_col1.text_input("시작일", value="", key="crawling_results_date_from")
    date_to = date_col2.text_input("종료일", value="", key="crawling_results_date_to")

    render_live_sheet_probe_section(schema_key=schema.key, year=year, month=month)
    try:
        result = load_crawling_results(schema.key, year, month)
    except Exception as exc:
        st.error(f"결과 조회 실패: {exc}")
        return

    if result.from_cache:
        st.warning("Google Sheets 조회에 실패하여 로컬 캐시를 표시합니다.")
    if result.spreadsheet_url:
        st.link_button("원본 Google Sheet", result.spreadsheet_url)

    df = result.dataframe
    if df.empty:
        st.info("표시할 결과가 없습니다.")
        return

    filtered = filter_results_dataframe(df, query=query, date_from=date_from, date_to=date_to)
    _render_summary(summarize_results_dataframe(filtered))
    _render_chart(schema, filtered)
    st.dataframe(filtered, use_container_width=True)
    st.download_button(
        "CSV 다운로드",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{schema.key}.csv",
        mime="text/csv",
    )
