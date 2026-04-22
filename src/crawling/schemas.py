from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.crawling.daily_trend_writer import (
    EARLY_SIGNAL_TAB,
    FLOW_SIGNAL_TAB,
    KR_TAB,
    NEWS_TAB,
    THEME_CLUSTER_TAB,
    THEME_TREND_TAB,
    US_TAB,
)


WorkbookKind = Literal["monthly", "trend", "flow"]


@dataclass(frozen=True)
class ResultSheetSchema:
    key: str
    label: str
    workbook_kind: WorkbookKind
    worksheet_title: str
    market: str
    category: str
    spreadsheet_id_env: str
    a1_range: str = "A1:Z"

    def workbook_title(self, *, year: int | None = None, month: str | None = None) -> str:
        if self.workbook_kind == "monthly":
            if not month:
                raise ValueError(f"{self.key} requires month")
            return f"주식_쉐도잉_{month}"
        if self.workbook_kind == "trend":
            if year is None:
                raise ValueError(f"{self.key} requires year")
            return f"시장트렌드_{int(year)}"
        if self.workbook_kind == "flow":
            if year is None:
                raise ValueError(f"{self.key} requires year")
            return f"시장흐름_{int(year)}"
        raise ValueError(f"Unsupported workbook kind: {self.workbook_kind}")


RESULT_SHEET_SCHEMAS: dict[str, ResultSheetSchema] = {
    "kr_surge": ResultSheetSchema(
        key="kr_surge",
        label="KR 급등주",
        workbook_kind="monthly",
        worksheet_title="급등주_쉐도잉",
        market="KR",
        category="shadowing",
        spreadsheet_id_env="SHEET_ID_SHADOWING",
    ),
    "kr_volume": ResultSheetSchema(
        key="kr_volume",
        label="KR 거래대금",
        workbook_kind="monthly",
        worksheet_title="거래대금_쉐도잉",
        market="KR",
        category="shadowing",
        spreadsheet_id_env="SHEET_ID_SHADOWING",
    ),
    "kr_drop": ResultSheetSchema(
        key="kr_drop",
        label="KR 낙폭과대",
        workbook_kind="monthly",
        worksheet_title="낙폭과대_쉐도잉",
        market="KR",
        category="shadowing",
        spreadsheet_id_env="SHEET_ID_SHADOWING",
    ),
    "us_surge": ResultSheetSchema(
        key="us_surge",
        label="US 급등주",
        workbook_kind="monthly",
        worksheet_title="미국_급등주_쉐도잉",
        market="US",
        category="shadowing",
        spreadsheet_id_env="SHEET_ID_SHADOWING",
    ),
    "us_volume": ResultSheetSchema(
        key="us_volume",
        label="US 거래대금",
        workbook_kind="monthly",
        worksheet_title="미국_거래대금_쉐도잉",
        market="US",
        category="shadowing",
        spreadsheet_id_env="SHEET_ID_SHADOWING",
    ),
    "us_drop": ResultSheetSchema(
        key="us_drop",
        label="US 낙폭과대",
        workbook_kind="monthly",
        worksheet_title="미국_낙폭과대_쉐도잉",
        market="US",
        category="shadowing",
        spreadsheet_id_env="SHEET_ID_SHADOWING",
    ),
    "trend_kr_daily": ResultSheetSchema(
        key="trend_kr_daily",
        label="시장트렌드 KR 일별",
        workbook_kind="trend",
        worksheet_title=KR_TAB,
        market="KR",
        category="trend",
        spreadsheet_id_env="SHEET_ID_TREND",
    ),
    "trend_us_daily": ResultSheetSchema(
        key="trend_us_daily",
        label="시장트렌드 US 일별",
        workbook_kind="trend",
        worksheet_title=US_TAB,
        market="US",
        category="trend",
        spreadsheet_id_env="SHEET_ID_TREND",
    ),
    "trend_news": ResultSheetSchema(
        key="trend_news",
        label="뉴스 요약",
        workbook_kind="trend",
        worksheet_title=NEWS_TAB,
        market="ALL",
        category="trend",
        spreadsheet_id_env="SHEET_ID_TREND",
    ),
    "flow_theme_clusters": ResultSheetSchema(
        key="flow_theme_clusters",
        label="테마 클러스터 일별",
        workbook_kind="flow",
        worksheet_title=THEME_CLUSTER_TAB,
        market="KR",
        category="flow",
        spreadsheet_id_env="SHEET_ID_FLOW",
    ),
    "flow_theme_trends": ResultSheetSchema(
        key="flow_theme_trends",
        label="테마 트렌드 주간",
        workbook_kind="flow",
        worksheet_title=THEME_TREND_TAB,
        market="KR",
        category="flow",
        spreadsheet_id_env="SHEET_ID_FLOW",
    ),
    "flow_early_signals": ResultSheetSchema(
        key="flow_early_signals",
        label="조기신호 관찰",
        workbook_kind="flow",
        worksheet_title=EARLY_SIGNAL_TAB,
        market="KR",
        category="flow",
        spreadsheet_id_env="SHEET_ID_FLOW",
    ),
    "flow_reversal_signals": ResultSheetSchema(
        key="flow_reversal_signals",
        label="수급전환 포착",
        workbook_kind="flow",
        worksheet_title=FLOW_SIGNAL_TAB,
        market="KR",
        category="flow",
        spreadsheet_id_env="SHEET_ID_FLOW",
    ),
}


def get_result_sheet_schema(key: str) -> ResultSheetSchema:
    try:
        return RESULT_SHEET_SCHEMAS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown result sheet schema: {key}") from exc


def list_result_sheet_schemas() -> tuple[ResultSheetSchema, ...]:
    return tuple(RESULT_SHEET_SCHEMAS.values())
