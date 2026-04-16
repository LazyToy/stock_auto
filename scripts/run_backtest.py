"""Backtest runner for indicator strategies."""

import argparse
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
from dotenv import load_dotenv

from src.backtest.engine import BacktestEngine
from src.data.api_client import KISAPIClient
from src.strategies.base import BaseStrategy
from src.utils.runtime_clients import build_kis_client
from src.utils.runtime_logging import configure_script_logging
from src.utils.runtime_strategies import INDICATOR_STRATEGY_CHOICES, build_indicator_strategy

try:
    from src.strategies.ml_strategy import (
        FeatureEngineering,
        MLPrediction,
        StrategyFactory as MLStrategyFactory,
    )

    ML_STRATEGY_AVAILABLE = True
except ImportError:
    ML_STRATEGY_AVAILABLE = False


ML_BACKTEST_CHOICES = ["ml_rf", "ml_gb", "ensemble"]
BACKTEST_STRATEGY_CHOICES = INDICATOR_STRATEGY_CHOICES + ML_BACKTEST_CHOICES


def create_ml_strategy(strategy_name: str):
    mapped_name = "ml_ensemble" if strategy_name == "ensemble" else strategy_name
    return MLStrategyFactory.create(mapped_name)


class WalkForwardMLStrategy(BaseStrategy):
    """Train an ML strategy only on past data and emit time-series signals."""

    LABELS = {
        "ml_rf": "RandomForest",
        "ml_gb": "GradientBoosting",
        "ensemble": "Ensemble",
    }

    def __init__(
        self,
        strategy_name: str,
        min_train_size: int = 120,
        retrain_interval: int = 1,
        symbol: str | None = None,
    ):
        label = self.LABELS.get(strategy_name, strategy_name)
        super().__init__(name=f"WalkForward({label})")
        self.strategy_name = strategy_name
        self.min_train_size = min_train_size
        self.retrain_interval = max(1, retrain_interval)
        self.symbol = symbol
        self.evaluation_summary = {
            "symbol": symbol,
            "predictions": 0,
            "trained_predictions": 0,
            "untrained_predictions": 0,
            "evaluable": 0,
            "evaluable_predictions": 0,
            "unevaluable_trained_predictions": 0,
            "correct_predictions": 0,
            "incorrect_predictions": 0,
            "coverage": 0.0,
            "accuracy": 0.0,
            "retrain_count": 0,
            "label_forward_days": 5,
            "label_threshold": 0.02,
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        result = data.copy()
        result["signal"] = 0

        if len(data) <= self.min_train_size:
            return result

        current_strategy = None
        last_train_size = None
        retrain_count = 0
        prediction_history = []

        for idx in range(self.min_train_size, len(data)):
            train_size = idx
            should_retrain = (
                current_strategy is None
                or last_train_size is None
                or train_size - last_train_size >= self.retrain_interval
            )

            if should_retrain:
                current_strategy = create_ml_strategy(self.strategy_name)
                current_strategy.train(data.iloc[:idx].copy())
                last_train_size = train_size
                retrain_count += 1

            prediction = current_strategy.predict(data.iloc[: idx + 1].copy())
            result.iloc[idx, result.columns.get_loc("signal")] = prediction.signal
            prediction_history.append(
                {
                    "index": result.index[idx],
                    "signal": int(prediction.signal),
                    "trained": bool(getattr(current_strategy, "is_trained", True)),
                }
            )

        self.evaluation_summary = self._build_evaluation_summary(
            data,
            prediction_history,
            retrain_count,
        )
        return result

    def _build_evaluation_summary(
        self,
        data: pd.DataFrame,
        prediction_history: list[dict],
        retrain_count: int,
    ) -> dict:
        predictions = len(prediction_history)
        if predictions == 0:
            return {
                "symbol": self.symbol,
                "predictions": 0,
                "trained_predictions": 0,
                "untrained_predictions": 0,
                "evaluable": 0,
                "evaluable_predictions": 0,
                "unevaluable_trained_predictions": 0,
                "correct_predictions": 0,
                "incorrect_predictions": 0,
                "coverage": 0.0,
                "accuracy": 0.0,
                "retrain_count": retrain_count,
                "label_forward_days": 5,
                "label_threshold": 0.02,
            }

        labeled = FeatureEngineering.create_labels(data.copy())
        labels = labeled["label"].to_dict() if "label" in labeled.columns else {}

        trained_predictions = 0
        evaluable = 0
        correct = 0

        for item in prediction_history:
            if not item["trained"]:
                continue

            trained_predictions += 1
            actual = labels.get(item["index"])
            if actual is None or pd.isna(actual):
                continue

            evaluable += 1
            if int(actual) == int(item["signal"]):
                correct += 1

        accuracy = correct / evaluable if evaluable else 0.0
        coverage = evaluable / predictions if predictions else 0.0
        return {
            "symbol": self.symbol,
            "predictions": predictions,
            "trained_predictions": trained_predictions,
            "untrained_predictions": predictions - trained_predictions,
            "evaluable": evaluable,
            "evaluable_predictions": evaluable,
            "unevaluable_trained_predictions": trained_predictions - evaluable,
            "correct_predictions": correct,
            "incorrect_predictions": evaluable - correct,
            "coverage": coverage,
            "accuracy": accuracy,
            "retrain_count": retrain_count,
            "label_forward_days": 5,
            "label_threshold": 0.02,
        }

    def get_evaluation_summary(self) -> dict:
        return dict(self.evaluation_summary)


def build_backtest_strategy(
    strategy_name: str,
    data: pd.DataFrame,
    *,
    walk_forward: bool = True,
    min_train_size: int = 120,
    retrain_interval: int = 1,
    symbol: str | None = None,
):
    if strategy_name in INDICATOR_STRATEGY_CHOICES:
        return build_indicator_strategy(strategy_name)

    if not ML_STRATEGY_AVAILABLE:
        raise ImportError("ML strategy support is unavailable")

    if walk_forward:
        return WalkForwardMLStrategy(
            strategy_name,
            min_train_size=min_train_size,
            retrain_interval=retrain_interval,
            symbol=symbol,
        )

    strategy = create_ml_strategy(strategy_name)
    strategy.train(data)
    return strategy


def setup_logging():
    configure_script_logging(
        file_name="backtest.log",
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def build_walk_forward_report(
    strategy,
    *,
    symbol: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    summary = None
    if hasattr(strategy, "get_evaluation_summary") and callable(strategy.get_evaluation_summary):
        summary = strategy.get_evaluation_summary()
    elif hasattr(strategy, "evaluation_summary"):
        summary = getattr(strategy, "evaluation_summary")

    if not summary:
        return None

    predictions = int(summary.get("predictions", 0))
    if predictions <= 0:
        return None

    report = dict(summary)
    if symbol is not None:
        report["symbol"] = symbol
    if start is not None:
        report["start"] = start
    if end is not None:
        report["end"] = end
    return report


def print_walk_forward_summary(
    strategy,
    *,
    symbol: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    report = build_walk_forward_report(strategy, symbol=symbol, start=start, end=end)
    if not report:
        return

    predictions = int(report.get("predictions", 0))
    evaluable = int(report.get("evaluable_predictions", report.get("evaluable", 0)))
    trained_predictions = int(report.get("trained_predictions", 0))
    coverage = float(report.get("coverage", 0.0))
    accuracy = float(report.get("accuracy", 0.0))
    retrain_count = int(report.get("retrain_count", 0))
    label_forward_days = int(report.get("label_forward_days", 5))
    label_threshold = float(report.get("label_threshold", 0.02))
    report_symbol = report.get("symbol")
    report_start = report.get("start")
    report_end = report.get("end")

    print("\n=== Walk-forward evaluation ===")
    if report_symbol:
        print(f"Symbol: {report_symbol}")
    if report_start or report_end:
        start_label = report_start or "N/A"
        end_label = report_end or "N/A"
        print(f"Period: {start_label} ~ {end_label}")
    print(f"Predictions: {predictions}")
    print(f"Trained predictions: {trained_predictions}")
    print(f"Evaluable: {evaluable}")
    print(f"Coverage: {coverage:.2f}")
    print(f"Accuracy: {accuracy:.2f}")
    print(f"Retrain count: {retrain_count}")
    print(f"Label spec: {label_forward_days}d / ±{label_threshold:.2%}")


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Run a stock backtest")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol code, for example 005930")
    parser.add_argument(
        "--strategy",
        type=str,
        default="ma",
        choices=BACKTEST_STRATEGY_CHOICES,
        help="Strategy selection",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=(datetime.now() - timedelta(days=365)).strftime("%Y%m%d"),
        help="Start date (YYYYMMDD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=datetime.now().strftime("%Y%m%d"),
        help="End date (YYYYMMDD)",
    )
    parser.add_argument("--capital", type=float, default=10000000, help="Initial capital")
    parser.add_argument(
        "--walk-forward",
        dest="walk_forward",
        action="store_true",
        help="Use walk-forward training for ML strategies",
    )
    parser.add_argument(
        "--no-walk-forward",
        dest="walk_forward",
        action="store_false",
        help="Disable walk-forward training for ML strategies",
    )
    parser.set_defaults(walk_forward=True)
    parser.add_argument(
        "--min-train-size",
        type=int,
        default=120,
        help="Minimum rows before the first walk-forward ML fit",
    )
    parser.add_argument(
        "--retrain-interval",
        type=int,
        default=1,
        help="Number of rows between walk-forward ML retrains",
    )
    args = parser.parse_args()

    strategy = None
    strategy_label = args.strategy
    if args.strategy in INDICATOR_STRATEGY_CHOICES:
        strategy = build_backtest_strategy(
            args.strategy,
            pd.DataFrame(),
            walk_forward=getattr(args, "walk_forward", True),
            min_train_size=getattr(args, "min_train_size", 120),
            retrain_interval=getattr(args, "retrain_interval", 1),
            symbol=args.symbol,
        )
        strategy_label = strategy.name

    print(f"=== Backtest start: {args.symbol} ===")
    print(f"Strategy: {strategy_label}")
    print(f"Period: {args.start} ~ {args.end}")

    load_dotenv()
    client = build_kis_client(
        app_key=os.getenv("KIS_APP_KEY"),
        app_secret=os.getenv("KIS_APP_SECRET"),
        account_number=os.getenv("KIS_ACCOUNT_NUMBER"),
        is_mock=True,
        client_cls=KISAPIClient,
    )

    print("Downloading price data...")
    try:
        prices = client.get_daily_price_history(args.symbol, args.start, args.end)
        data = pd.DataFrame([vars(p) for p in prices])

        if data.empty:
            print("No data available.")
            return

        if strategy is None:
            strategy = build_backtest_strategy(
                args.strategy,
                data,
                walk_forward=getattr(args, "walk_forward", True),
                min_train_size=getattr(args, "min_train_size", 120),
                retrain_interval=getattr(args, "retrain_interval", 1),
                symbol=args.symbol,
            )
        engine = BacktestEngine(strategy, args.symbol, data, args.capital)
        result = engine.run()

        print("\n=== Result Report ===")
        print(f"Total return: {result.total_return:.2f}%")
        print(f"Absolute profit: {result.portfolio.total_value - args.capital:,.0f}")
        print(f"Final assets: {result.portfolio.total_value:,.0f}")
        print(f"MDD: {result.max_drawdown:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Trade count: {len(result.trades)}")
        print_walk_forward_summary(
            strategy,
            symbol=args.symbol,
            start=args.start,
            end=args.end,
        )
    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
