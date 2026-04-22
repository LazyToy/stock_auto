"""Backward-compatible shim for the migrated us_stock_scraper module."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_module = importlib.import_module("src.crawling.us_stock_scraper")

CONFIG = _module.CONFIG
Credentials = _module.Credentials
_DEFAULT_CREDENTIALS = Credentials
resolve_service_account_file = _module.resolve_service_account_file
make_sheet_month = _module.make_sheet_month
make_row_date = _module.make_row_date
ensure_worksheet = _module.ensure_worksheet
decode_tv_row = _module.decode_tv_row
get_tradingview_data = _module.get_tradingview_data
get_yahoo_rss_news = _module.get_yahoo_rss_news
get_naver_us_news = _module.get_naver_us_news
get_chart_formulas = _module.get_chart_formulas
get_existing_keys = _module.get_existing_keys
resize_cells_for_images = _module.resize_cells_for_images


def _sync_patchable_globals() -> None:
    global Credentials
    _module.gspread = importlib.import_module("gspread")
    if Credentials is _DEFAULT_CREDENTIALS:
        Credentials = importlib.import_module("google.oauth2.service_account").Credentials
    _module.Credentials = Credentials
    _module.resolve_service_account_file = resolve_service_account_file


def get_google_sheet(today_str):
    _sync_patchable_globals()
    return _module.get_google_sheet(today_str)


def main():
    _sync_patchable_globals()
    return _module.main()

__all__ = [
    "CONFIG",
    "Credentials",
    "resolve_service_account_file",
    "make_sheet_month",
    "make_row_date",
    "get_google_sheet",
    "ensure_worksheet",
    "decode_tv_row",
    "get_tradingview_data",
    "get_yahoo_rss_news",
    "get_naver_us_news",
    "get_chart_formulas",
    "get_existing_keys",
    "resize_cells_for_images",
    "main",
]
