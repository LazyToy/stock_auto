"""Backward-compatible shim for the migrated stock_scraper module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.stock_scraper")

CONFIG = _module.CONFIG
Credentials = _module.Credentials
_DEFAULT_CREDENTIALS = Credentials
resolve_service_account_file = _module.resolve_service_account_file
get_naver_news = _module.get_naver_news
get_chart_formulas = _module.get_chart_formulas
ensure_worksheet = _module.ensure_worksheet
get_existing_keys = _module.get_existing_keys
resize_cells_for_images = _module.resize_cells_for_images
infer_volume_unit = _module.infer_volume_unit
resolve_trading_date = _module.resolve_trading_date
dry_run_indicator_check = _module.dry_run_indicator_check
enrich_with_indicators = _module.enrich_with_indicators


def _sync_patchable_globals() -> None:
    global Credentials
    _module.gspread = importlib.import_module("gspread")
    if Credentials is _DEFAULT_CREDENTIALS:
        Credentials = importlib.import_module("google.oauth2.service_account").Credentials
    _module.Credentials = Credentials
    _module.resolve_service_account_file = resolve_service_account_file
    _module.dry_run_indicator_check = dry_run_indicator_check


def get_gspread_client():
    _sync_patchable_globals()
    return _module.get_gspread_client()


def main():
    _sync_patchable_globals()
    return _module.main()

__all__ = [
    "CONFIG",
    "Credentials",
    "resolve_service_account_file",
    "get_naver_news",
    "get_chart_formulas",
    "get_gspread_client",
    "ensure_worksheet",
    "get_existing_keys",
    "resize_cells_for_images",
    "infer_volume_unit",
    "resolve_trading_date",
    "dry_run_indicator_check",
    "enrich_with_indicators",
    "main",
]
