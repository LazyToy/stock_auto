from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

import pandas as pd

from src.crawling.schemas import get_result_sheet_schema
from src.crawling.sheets_reader import (
    LiveSheetBackendStatus,
    build_live_sheet_probe_request,
    describe_live_sheet_backend,
    SheetReadRequest,
    probe_live_sheet_access,
    load_cached_dataframe,
    read_sheet_dataframe,
    values_to_dataframe,
)


class FakeWorksheet:
    def __init__(self, values: list[list[object]]) -> None:
        self._values = values

    def get_all_values(self) -> list[list[object]]:
        return self._values


class FakeSpreadsheet:
    def __init__(self, title: str, worksheets: dict[str, FakeWorksheet]) -> None:
        self.title = title
        self.url = f"https://docs.google.com/spreadsheets/d/{title}"
        self._worksheets = worksheets

    def worksheet(self, title: str) -> FakeWorksheet:
        return self._worksheets[title]


class FakeClient:
    def __init__(self, spreadsheet: FakeSpreadsheet) -> None:
        self.spreadsheet = spreadsheet
        self.open_calls: list[str] = []
        self.open_by_key_calls: list[str] = []

    def open(self, title: str) -> FakeSpreadsheet:
        self.open_calls.append(title)
        return self.spreadsheet

    def open_by_key(self, spreadsheet_id: str) -> FakeSpreadsheet:
        self.open_by_key_calls.append(spreadsheet_id)
        return self.spreadsheet


def test_values_to_dataframe_uses_first_row_as_headers_and_pads_short_rows() -> None:
    df = values_to_dataframe(
        [
            ["날짜", "종목", "등락률"],
            ["2026-04-20", "삼성전자", 3.2],
            ["2026-04-21", "SK하이닉스"],
            [],
        ]
    )

    assert list(df.columns) == ["날짜", "종목", "등락률"]
    assert df.to_dict("records") == [
        {"날짜": "2026-04-20", "종목": "삼성전자", "등락률": 3.2},
        {"날짜": "2026-04-21", "종목": "SK하이닉스", "등락률": ""},
    ]


def test_read_sheet_dataframe_opens_workbook_by_schema_title() -> None:
    schema = get_result_sheet_schema("kr_surge")
    spreadsheet = FakeSpreadsheet(
        "주식_쉐도잉_202604",
        {"급등주_쉐도잉": FakeWorksheet([["날짜", "종목"], ["2026-04-20", "삼성전자"]])},
    )
    client = FakeClient(spreadsheet)

    result = read_sheet_dataframe(
        SheetReadRequest(schema=schema, month="202604"),
        client_factory=lambda: client,
    )

    assert client.open_calls == ["주식_쉐도잉_202604"]
    assert client.open_by_key_calls == []
    assert result.workbook_title == "주식_쉐도잉_202604"
    assert result.worksheet_title == "급등주_쉐도잉"
    assert result.spreadsheet_url == spreadsheet.url
    assert result.dataframe.to_dict("records") == [{"날짜": "2026-04-20", "종목": "삼성전자"}]


def test_read_sheet_dataframe_prefers_env_spreadsheet_id(monkeypatch) -> None:
    schema = get_result_sheet_schema("flow_theme_clusters")
    spreadsheet = FakeSpreadsheet(
        "시장흐름_2026",
        {"테마클러스터_일별": FakeWorksheet([["날짜", "섹터"], ["2026-04-20", "반도체"]])},
    )
    client = FakeClient(spreadsheet)
    monkeypatch.setenv("SHEET_ID_FLOW", "flow-id-123")

    result = read_sheet_dataframe(
        SheetReadRequest(schema=schema, year=2026),
        client_factory=lambda: client,
    )

    assert client.open_calls == []
    assert client.open_by_key_calls == ["flow-id-123"]
    assert result.dataframe.iloc[0]["섹터"] == "반도체"


def test_read_sheet_dataframe_writes_sqlite_cache_and_falls_back() -> None:
    schema = get_result_sheet_schema("trend_kr_daily")
    spreadsheet = FakeSpreadsheet(
        "시장트렌드_2026",
        {"KR_일별": FakeWorksheet([["날짜", "상승"], ["2026-04-20", 812]])},
    )
    cache_dir = Path.cwd() / ".pytest_tmp" / "phase29_sheets_cache"
    good_client = FakeClient(spreadsheet)

    first = read_sheet_dataframe(
        SheetReadRequest(schema=schema, year=2026),
        client_factory=lambda: good_client,
        cache_dir=cache_dir,
    )

    assert first.dataframe.iloc[0]["상승"] == 812

    def failing_factory():
        raise RuntimeError("network down")

    second = read_sheet_dataframe(
        SheetReadRequest(schema=schema, year=2026),
        client_factory=failing_factory,
        cache_dir=cache_dir,
        fallback_to_cache=True,
    )

    assert second.from_cache is True
    assert second.dataframe.to_dict("records") == [{"날짜": "2026-04-20", "상승": 812}]


def test_load_cached_dataframe_returns_none_when_cache_is_missing() -> None:
    schema = get_result_sheet_schema("trend_us_daily")

    cached = load_cached_dataframe(
        SheetReadRequest(schema=schema, year=2026),
        cache_dir=Path.cwd() / ".pytest_tmp" / "phase29_missing_cache",
    )

    assert cached is None


def test_describe_live_sheet_backend_reports_missing_requirements() -> None:
    status = describe_live_sheet_backend(
        env={},
        service_account_file="missing.json",
        path_exists=lambda path: False,
    )

    assert isinstance(status, LiveSheetBackendStatus)
    assert status.service_account_configured is False
    assert status.live_probe_ready is False
    assert "SHEET_ID_FLOW" in status.missing_spreadsheet_id_envs
    assert "SHEET_ID_SHADOWING" in status.missing_spreadsheet_id_envs
    assert "SHEET_ID_TREND" in status.missing_spreadsheet_id_envs


def test_describe_live_sheet_backend_allows_title_lookup_without_sheet_ids() -> None:
    status = describe_live_sheet_backend(
        env={},
        service_account_file="config/google_service_account.json",
        path_exists=lambda path: True,
    )

    assert status.service_account_configured is True
    assert status.missing_spreadsheet_id_envs
    assert status.live_probe_ready is True


def test_build_live_sheet_probe_request_uses_schema_defaults() -> None:
    monthly = build_live_sheet_probe_request("kr_surge", now=datetime(2026, 4, 21, 9, 0, 0))
    yearly = build_live_sheet_probe_request("trend_kr_daily", now=datetime(2026, 4, 21, 9, 0, 0))

    assert monthly.schema.key == "kr_surge"
    assert monthly.month == "202604"
    assert monthly.year is None
    assert yearly.schema.key == "trend_kr_daily"
    assert yearly.year == 2026
    assert yearly.month is None


def test_probe_live_sheet_access_uses_live_read_without_cache_fallback() -> None:
    calls = []

    def fake_read(request, **kwargs):
        calls.append((request, kwargs))
        return SimpleNamespace(
            request=request,
            workbook_title=request.workbook_title(),
            worksheet_title=request.schema.worksheet_title,
            dataframe=pd.DataFrame([{"date": "2026-04-21", "ticker": "AAPL"}]),
            spreadsheet_url="https://docs.google.com/spreadsheets/d/live-probe",
            from_cache=False,
        )

    result = probe_live_sheet_access(
        "trend_kr_daily",
        year=2026,
        read_dataframe=fake_read,
    )

    assert result.schema_key == "trend_kr_daily"
    assert result.row_count == 1
    assert result.spreadsheet_url == "https://docs.google.com/spreadsheets/d/live-probe"
    assert result.from_cache is False
    assert calls[0][1]["fallback_to_cache"] is False
