from __future__ import annotations

from src.crawling.schemas import (
    RESULT_SHEET_SCHEMAS,
    get_result_sheet_schema,
    list_result_sheet_schemas,
)


def test_phase5_schema_registry_covers_expected_result_sets() -> None:
    keys = {schema.key for schema in list_result_sheet_schemas()}

    assert keys == {
        "kr_surge",
        "kr_volume",
        "kr_drop",
        "us_surge",
        "us_volume",
        "us_drop",
        "trend_kr_daily",
        "trend_us_daily",
        "trend_news",
        "flow_theme_clusters",
        "flow_theme_trends",
        "flow_early_signals",
        "flow_reversal_signals",
    }


def test_phase5_schema_builds_shadowing_workbook_title_from_month() -> None:
    schema = get_result_sheet_schema("kr_surge")

    assert schema.workbook_title(month="202604") == "주식_쉐도잉_202604"
    assert schema.worksheet_title == "급등주_쉐도잉"
    assert schema.spreadsheet_id_env == "SHEET_ID_SHADOWING"


def test_phase5_schema_builds_yearly_workbook_titles() -> None:
    trend = RESULT_SHEET_SCHEMAS["trend_kr_daily"]
    flow = RESULT_SHEET_SCHEMAS["flow_theme_clusters"]

    assert trend.workbook_title(year=2026) == "시장트렌드_2026"
    assert trend.worksheet_title == "KR_일별"
    assert trend.spreadsheet_id_env == "SHEET_ID_TREND"
    assert flow.workbook_title(year=2026) == "시장흐름_2026"
    assert flow.worksheet_title == "테마클러스터_일별"
    assert flow.spreadsheet_id_env == "SHEET_ID_FLOW"


def test_phase5_schema_requires_month_or_year_for_matching_workbook() -> None:
    monthly = get_result_sheet_schema("us_drop")
    yearly = get_result_sheet_schema("flow_early_signals")

    try:
        monthly.workbook_title(year=2026)
    except ValueError as exc:
        assert "month" in str(exc)
    else:
        raise AssertionError("expected monthly workbook without month to fail")

    try:
        yearly.workbook_title(month="202604")
    except ValueError as exc:
        assert "year" in str(exc)
    else:
        raise AssertionError("expected yearly workbook without year to fail")
