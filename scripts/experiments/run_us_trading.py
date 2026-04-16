"""US auto-trading runtime script."""

import logging
import os
import schedule
import sys
import time

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.data.api_client import KISAPIClient
from src.trader.auto_trader import AutoTrader
from src.utils.execution_mode import describe_execution_mode
from src.utils.runtime_clients import build_kis_client
from src.utils.runtime_logging import configure_script_logging

logger = logging.getLogger("US_AutoTrading")
_LOGGING_CONFIGURED = False
DEFAULT_BROKER_IS_MOCK = True
DEFAULT_DRY_RUN = True


def configure_logging():
    """Configure logging only once per process."""
    global _LOGGING_CONFIGURED
    _LOGGING_CONFIGURED = configure_script_logging(
        file_name="us_trading.log",
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        configured=_LOGGING_CONFIGURED,
    )


def job():
    configure_logging()
    try:
        logger.info("US auto-trading job starting")
        logger.info(
            f"Execution mode: {describe_execution_mode(DEFAULT_BROKER_IS_MOCK, DEFAULT_DRY_RUN)}"
        )

        load_dotenv()
        api_client = build_kis_client(
            app_key=Config.KIS_APP_KEY,
            app_secret=Config.KIS_APP_SECRET,
            account_number=Config.KIS_ACCOUNT_NUMBER,
            is_mock=DEFAULT_BROKER_IS_MOCK,
            market="US",
            client_cls=KISAPIClient,
        )

        universe = Config.load_universe().get("US", [])
        if not universe:
            raise ValueError("Universe config is missing 'US' entries in config/universe.json")

        trader = AutoTrader(
            api_client=api_client,
            universe=universe,
            max_stocks=3,
            dry_run=DEFAULT_DRY_RUN,
            market="US",
        )
        trader.run_daily_routine()
    except Exception as exc:
        logger.error(f"Job failed: {exc}")


if __name__ == "__main__":
    configure_logging()
    logger.info("US auto-trading scheduler initialized")
    schedule.every().day.at("23:30").do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)
