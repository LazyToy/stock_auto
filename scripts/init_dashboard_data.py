"""Initialize dashboard snapshot data for KR and US markets."""

import os
import sys

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.data.api_client import KISAPIClient
from src.trader.auto_trader import AutoTrader
from src.utils.runtime_clients import build_kis_client


def main():
    load_dotenv()

    try:
        print("Initializing KR dashboard data...")
        client_kr = build_kis_client(
            app_key=Config.KIS_APP_KEY,
            app_secret=Config.KIS_APP_SECRET,
            account_number=Config.KIS_ACCOUNT_NUMBER,
            is_mock=True,
            market="KR",
            client_cls=KISAPIClient,
        )
        trader_kr = AutoTrader(client_kr, universe=[], market="KR")
        trader_kr.export_dashboard_state()
        print("KR data exported.")
    except Exception as exc:
        print(f"KR init failed: {exc}")

    try:
        print("Initializing US dashboard data...")
        client_us = build_kis_client(
            app_key=Config.KIS_APP_KEY,
            app_secret=Config.KIS_APP_SECRET,
            account_number=Config.KIS_ACCOUNT_NUMBER,
            is_mock=True,
            market="US",
            client_cls=KISAPIClient,
        )
        trader_us = AutoTrader(client_us, universe=[], market="US")
        trader_us.export_dashboard_state()
        print("US data exported.")
    except Exception as exc:
        print(f"US init failed: {exc}")


if __name__ == "__main__":
    main()
