"""Live trading runner with explicit broker/order-mode controls."""

import argparse
import logging
import os

from dotenv import load_dotenv

from src.broker.kis import KISBroker
from src.data.api_client import KISAPIClient
from src.live.engine import LiveTradingEngine
from src.utils.execution_mode import (
    CONFIRM_ORDER_SUBMISSION_FLAG_HELP,
    CONFIRM_REAL_BROKER_FLAG_HELP,
    DRY_RUN_FLAG_HELP,
    LIVE_FLAG_HELP,
    MOCK_ORDER_FLAG_HELP,
    REAL_BROKER_FLAG_HELP,
    add_execution_mode_arguments,
    describe_execution_mode,
    emit_execution_banner,
    load_kis_credentials,
    resolve_execution_flags,
    validate_execution_mode_or_exit,
)
from src.utils.runtime_clients import build_kis_broker, build_kis_client
from src.utils.runtime_logging import configure_script_logging
from src.utils.runtime_strategies import INDICATOR_STRATEGY_CHOICES, build_indicator_strategy


def setup_logging():
    configure_script_logging(
        file_name="trading.log",
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    parser = argparse.ArgumentParser(description="Live trading runner")
    parser.add_argument(
        "--symbols",
        type=str,
        required=True,
        help="Comma-separated symbol list, for example 005930,000660",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="ma",
        choices=INDICATOR_STRATEGY_CHOICES,
        help="Strategy selection",
    )
    add_execution_mode_arguments(
        parser,
        live_flag_help=LIVE_FLAG_HELP,
        include_legacy_mode=True,
        legacy_mode_help="legacy alias: mock -> --mock-order, real -> --real-broker",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("Main")
    load_dotenv()

    is_mock, dry_run = resolve_execution_flags(
        args,
        legacy_mode_attr="mode",
        legacy_mode_map={
            "mock": (True, False),
            "real": (False, False),
        },
    )

    emit_execution_banner(
        title="Live trading runner",
        details=[
            f"Strategy: {args.strategy}",
            f"Symbols: {args.symbols}",
        ],
        is_mock=is_mock,
        dry_run=dry_run,
    )

    validate_execution_mode_or_exit(
        args,
        is_mock=is_mock,
        dry_run=dry_run,
        real_broker_error="ERROR: real broker mode requires --confirm-real-broker",
    )

    app_key, app_secret, account = load_kis_credentials(
        is_mock=is_mock,
        getenv=os.getenv,
    )

    client = build_kis_client(
        app_key=app_key,
        app_secret=app_secret,
        account_number=account,
        is_mock=is_mock,
        client_cls=KISAPIClient,
    )
    broker = build_kis_broker(
        app_key=app_key,
        app_secret=app_secret,
        account_number=account,
        is_mock=is_mock,
        market="KR",
        broker_cls=KISBroker,
    )

    strategy = build_indicator_strategy(args.strategy)
    symbols = args.symbols.split(",")

    logger.info(f"Execution mode: {describe_execution_mode(is_mock, dry_run)}")
    logger.info(f"Target symbols: {symbols}")
    logger.info(f"Selected strategy: {strategy.name}")

    engine = LiveTradingEngine(
        strategy=strategy,
        symbols=symbols,
        api_client=client,
        broker=broker,
        check_interval=60,
        dry_run=dry_run,
    )

    engine.start()


if __name__ == "__main__":
    main()
