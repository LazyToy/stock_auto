"""Model training pipeline."""

import logging
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import Config
from src.data.api_client import KISAPIClient
from src.strategies.ml_strategy import MLStrategy, StrategyFactory
from src.utils.notification import send_notification
from src.utils.runtime_clients import build_kis_client

logger = logging.getLogger(__name__)


def train_monthly_model(market: str = "KR", strategy_type: str = "ml_rf"):
    """Train and save a monthly model snapshot for the selected market."""
    try:
        current_date = datetime.now()
        logger.info(f"[{market}] model retraining started ({strategy_type})")
        send_notification(
            f"[{market}] {current_date.strftime('%Y-%m')} monthly model retraining started"
        )

        universe = Config.load_universe().get(market, [])
        if not universe:
            logger.warning(f"[{market}] universe is empty; training stopped")
            return

        api_client = build_kis_client(
            market=market,
            is_mock=True,
            client_cls=KISAPIClient,
        )

        end_date_str = current_date.strftime("%Y%m%d")
        start_date_str = (current_date - timedelta(days=365)).strftime("%Y%m%d")
        logger.info(f"Collecting data ({start_date_str} ~ {end_date_str})")

        all_data = []
        for symbol in universe[:10]:
            try:
                prices = api_client.get_daily_price_history(symbol, start_date_str, end_date_str)
                df = pd.DataFrame([vars(price) for price in prices])
                if not df.empty:
                    df["symbol"] = symbol
                    all_data.append(df)
            except Exception as exc:
                logger.debug(f"{symbol} data collection failed: {exc}")

        if not all_data:
            logger.error("No training data collected.")
            return

        full_df = pd.concat(all_data, ignore_index=True)
        logger.info(f"Collected {len(full_df)} rows of data")

        strategy: MLStrategy = StrategyFactory.create(strategy_type)
        logger.info("Training model")
        strategy.train(full_df)

        os.makedirs("models", exist_ok=True)
        model_filename = f"models/{market.lower()}_{strategy_type}_{current_date.strftime('%Y%m')}.pkl"
        strategy.save_model(model_filename)

        logger.info(f"Model saved: {model_filename}")
        send_notification(f"[{market}] model retraining and save complete: {model_filename}")
    except Exception as exc:
        logger.error(f"Training failed: {exc}")
        send_notification(f"[{market}] model retraining failed: {exc}")
