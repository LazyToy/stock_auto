from __future__ import annotations

import importlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from src.crawling.schemas import ResultSheetSchema, get_result_sheet_schema, list_result_sheet_schemas
from src.crawling.service_account_path import resolve_service_account_file


DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "crawling" / "cache"
DEFAULT_CACHE_DB = "sheets_cache.sqlite3"
READONLY_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


@dataclass(frozen=True)
class SheetReadRequest:
    schema: ResultSheetSchema
    year: int | None = None
    month: str | None = None
    spreadsheet_id: str | None = None

    def workbook_title(self) -> str:
        return self.schema.workbook_title(year=self.year, month=self.month)


@dataclass(frozen=True)
class SheetReadResult:
    request: SheetReadRequest
    workbook_title: str
    worksheet_title: str
    dataframe: pd.DataFrame
    spreadsheet_url: str | None = None
    from_cache: bool = False


@dataclass(frozen=True)
class LiveSheetBackendStatus:
    service_account_file: str
    service_account_configured: bool
    configured_spreadsheet_id_envs: tuple[str, ...]
    missing_spreadsheet_id_envs: tuple[str, ...]
    live_probe_ready: bool


@dataclass(frozen=True)
class LiveSheetProbeResult:
    schema_key: str
    request: SheetReadRequest
    workbook_title: str
    worksheet_title: str
    row_count: int
    spreadsheet_url: str | None
    from_cache: bool


ClientFactory = Callable[[], Any]


def values_to_dataframe(values: list[list[Any]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()

    headers = [str(header) for header in values[0]]
    rows: list[list[Any]] = []
    for raw_row in values[1:]:
        if not raw_row or not any(str(cell).strip() for cell in raw_row):
            continue
        row = list(raw_row[: len(headers)])
        if len(row) < len(headers):
            row.extend([""] * (len(headers) - len(row)))
        rows.append(row)
    return pd.DataFrame(rows, columns=headers)


def make_sheet_client(service_account_file: str | None = None) -> Any:
    gspread = importlib.import_module("gspread")
    credentials_cls = importlib.import_module("google.oauth2.service_account").Credentials
    credentials = credentials_cls.from_service_account_file(
        resolve_service_account_file(service_account_file),
        scopes=READONLY_SCOPES,
    )
    return gspread.authorize(credentials)


def describe_live_sheet_backend(
    *,
    env: Mapping[str, str] | None = None,
    service_account_file: str | None = None,
    path_exists: Callable[[Path], bool] | None = None,
) -> LiveSheetBackendStatus:
    environment = env if env is not None else os.environ
    resolved_file = service_account_file or resolve_service_account_file()
    exists = path_exists or Path.exists
    service_account_path = Path(resolved_file)
    configured_envs = sorted(
        {
            schema.spreadsheet_id_env
            for schema in list_result_sheet_schemas()
            if environment.get(schema.spreadsheet_id_env)
        }
    )
    missing_envs = sorted(
        {
            schema.spreadsheet_id_env
            for schema in list_result_sheet_schemas()
            if not environment.get(schema.spreadsheet_id_env)
        }
    )
    service_account_configured = bool(resolved_file) and exists(service_account_path)
    return LiveSheetBackendStatus(
        service_account_file=str(service_account_path),
        service_account_configured=service_account_configured,
        configured_spreadsheet_id_envs=tuple(configured_envs),
        missing_spreadsheet_id_envs=tuple(missing_envs),
        live_probe_ready=service_account_configured,
    )


def build_live_sheet_probe_request(
    schema_key: str,
    *,
    year: int | None = None,
    month: str | None = None,
    now: datetime | None = None,
) -> SheetReadRequest:
    schema = get_result_sheet_schema(schema_key)
    current = now or datetime.now()
    if schema.workbook_kind == "monthly":
        return SheetReadRequest(
            schema=schema,
            month=month or current.strftime("%Y%m"),
        )
    return SheetReadRequest(
        schema=schema,
        year=year if year is not None else int(current.year),
    )


def probe_live_sheet_access(
    schema_key: str,
    *,
    request: SheetReadRequest | None = None,
    year: int | None = None,
    month: str | None = None,
    now: datetime | None = None,
    read_dataframe: Callable[..., SheetReadResult] | None = None,
) -> LiveSheetProbeResult:
    reader = read_dataframe or read_sheet_dataframe
    probe_request = request or build_live_sheet_probe_request(schema_key, year=year, month=month, now=now)
    result = reader(probe_request, fallback_to_cache=False)
    return LiveSheetProbeResult(
        schema_key=schema_key,
        request=probe_request,
        workbook_title=result.workbook_title,
        worksheet_title=result.worksheet_title,
        row_count=int(len(result.dataframe)),
        spreadsheet_url=result.spreadsheet_url,
        from_cache=bool(result.from_cache),
    )


def _cache_path(cache_dir: Path | str) -> Path:
    return Path(cache_dir) / DEFAULT_CACHE_DB


def _ensure_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sheet_cache (
            cache_key TEXT PRIMARY KEY,
            workbook_title TEXT NOT NULL,
            worksheet_title TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def _cache_key(request: SheetReadRequest) -> str:
    return "|".join(
        [
            request.schema.key,
            request.workbook_title(),
            request.schema.worksheet_title,
            request.spreadsheet_id or "",
        ]
    )


def store_cached_dataframe(
    request: SheetReadRequest,
    dataframe: pd.DataFrame,
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> None:
    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "columns": list(dataframe.columns),
        "rows": dataframe.to_dict("records"),
    }
    with sqlite3.connect(_cache_path(target_dir)) as conn:
        _ensure_cache_table(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO sheet_cache
                (cache_key, workbook_title, worksheet_title, fetched_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _cache_key(request),
                request.workbook_title(),
                request.schema.worksheet_title,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )


def load_cached_dataframe(
    request: SheetReadRequest,
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> pd.DataFrame | None:
    db_path = _cache_path(cache_dir)
    if not db_path.exists():
        return None

    with sqlite3.connect(db_path) as conn:
        _ensure_cache_table(conn)
        row = conn.execute(
            "SELECT payload FROM sheet_cache WHERE cache_key = ?",
            (_cache_key(request),),
        ).fetchone()
    if row is None:
        return None

    payload = json.loads(str(row[0]))
    return pd.DataFrame(payload.get("rows", []), columns=payload.get("columns", []))


def _resolve_spreadsheet_id(request: SheetReadRequest) -> str | None:
    if request.spreadsheet_id:
        return request.spreadsheet_id
    return os.getenv(request.schema.spreadsheet_id_env) or None


def _open_spreadsheet(client: Any, request: SheetReadRequest) -> Any:
    spreadsheet_id = _resolve_spreadsheet_id(request)
    if spreadsheet_id and hasattr(client, "open_by_key"):
        return client.open_by_key(spreadsheet_id)
    return client.open(request.workbook_title())


def _read_live_dataframe(request: SheetReadRequest, client_factory: ClientFactory) -> SheetReadResult:
    client = client_factory()
    spreadsheet = _open_spreadsheet(client, request)
    worksheet = spreadsheet.worksheet(request.schema.worksheet_title)
    dataframe = values_to_dataframe(worksheet.get_all_values())
    return SheetReadResult(
        request=request,
        workbook_title=request.workbook_title(),
        worksheet_title=request.schema.worksheet_title,
        dataframe=dataframe,
        spreadsheet_url=getattr(spreadsheet, "url", None),
    )


def read_sheet_dataframe(
    request: SheetReadRequest,
    *,
    client_factory: ClientFactory = make_sheet_client,
    cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
    fallback_to_cache: bool = True,
) -> SheetReadResult:
    try:
        result = _read_live_dataframe(request, client_factory)
    except Exception:
        if fallback_to_cache and cache_dir is not None:
            cached = load_cached_dataframe(request, cache_dir=cache_dir)
            if cached is not None:
                return SheetReadResult(
                    request=request,
                    workbook_title=request.workbook_title(),
                    worksheet_title=request.schema.worksheet_title,
                    dataframe=cached,
                    from_cache=True,
                )
        raise

    if cache_dir is not None:
        store_cached_dataframe(request, result.dataframe, cache_dir=cache_dir)
    return result
