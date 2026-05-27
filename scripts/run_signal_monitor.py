"""Run advisory AutoML signal monitoring for a watchlist."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.market_data import MarketDataFetcher
from src.monitoring.signal_monitor import AutomlSignalMonitor, SignalAlertStateStore
from src.optimization.automl_runtime import load_automl_artifacts_from_dir
from src.utils.config_loader import ConfigLoader
from src.utils.notification import send_notification

logger = logging.getLogger(__name__)


def parse_symbols(symbols: str | Iterable[str] | None) -> list[str]:
    """Parse a watchlist from CSV text or an iterable."""
    if symbols is None:
        return []
    raw_values = symbols if not isinstance(symbols, str) else symbols.split(",")
    parsed: list[str] = []
    for raw_symbol in raw_values:
        symbol = str(raw_symbol or "").strip().upper()
        if symbol and symbol not in parsed:
            parsed.append(symbol)
    return parsed


def load_watchlist(
    symbols: str | Iterable[str] | None,
    *,
    market: str = "korea",
    config_loader: ConfigLoader | None = None,
) -> list[str]:
    """Load explicit symbols first, then fall back to config watchlist."""
    explicit = parse_symbols(symbols)
    if explicit:
        return explicit
    loader = config_loader or ConfigLoader()
    try:
        return parse_symbols(loader.get_symbols(market))
    except Exception as exc:
        logger.warning("Could not load watchlist for market=%s: %s", market, exc)
        return []


def run_signal_monitor_once(
    *,
    symbols: list[str] | None = None,
    artifacts_dir: str | Path = "data/automl_params",
    period: str = "1y",
    state_path: str | Path = Path("data") / "automl_signal_alert_state.json",
    notify_on: Iterable[str] = ("BUY", "SELL"),
    artifact_loader: Callable[[str | Path], list[dict[str, Any]]] = load_automl_artifacts_from_dir,
    history_fetcher: Callable[[str, str], pd.DataFrame] | Any | None = None,
    notifier: Callable[[str], bool | None] = send_notification,
):
    """Run one advisory signal scan and return dispatch results."""
    artifacts = artifact_loader(artifacts_dir)
    fetcher = history_fetcher or MarketDataFetcher()
    state_store = SignalAlertStateStore(state_path)
    monitor = AutomlSignalMonitor(
        artifacts,
        history_fetcher=fetcher,
        notifier=notifier,
        period=period,
        notify_on=notify_on,
        state_store=state_store,
    )
    return monitor.scan_once(symbols)


def run_signal_monitor_loop(
    *,
    symbols: list[str] | None,
    artifacts_dir: str | Path,
    period: str,
    state_path: str | Path,
    interval_seconds: int,
    notify_on: Iterable[str] = ("BUY", "SELL"),
    iterations: int | None = None,
) -> None:
    """Run the signal monitor repeatedly. Intended for advisory alerts only."""
    interval = max(int(interval_seconds), 1)
    completed = 0
    while iterations is None or completed < iterations:
        results = run_signal_monitor_once(
            symbols=symbols,
            artifacts_dir=artifacts_dir,
            period=period,
            state_path=state_path,
            notify_on=notify_on,
        )
        if results:
            logger.info("Dispatched %s AutoML advisory signal(s)", len(results))
        completed += 1
        if iterations is not None and completed >= iterations:
            break
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Advisory AutoML signal monitor")
    parser.add_argument("--symbols", default="", help="Comma-separated watchlist")
    parser.add_argument("--market", default="korea", help="Config watchlist market when --symbols is empty")
    parser.add_argument("--artifacts-dir", default="data/automl_params")
    parser.add_argument("--period", default="1y")
    parser.add_argument("--state-path", default=str(Path("data") / "automl_signal_alert_state.json"))
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--notify-on", default="BUY,SELL", help="Comma-separated signal actions")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    symbols = load_watchlist(args.symbols, market=args.market)
    notify_on = parse_symbols(args.notify_on)
    if args.once:
        results = run_signal_monitor_once(
            symbols=symbols,
            artifacts_dir=args.artifacts_dir,
            period=args.period,
            state_path=args.state_path,
            notify_on=notify_on,
        )
        print(f"Dispatched {len(results)} AutoML advisory signal(s).")
        return

    run_signal_monitor_loop(
        symbols=symbols,
        artifacts_dir=args.artifacts_dir,
        period=args.period,
        state_path=args.state_path,
        interval_seconds=args.interval,
        notify_on=notify_on,
    )


if __name__ == "__main__":
    main()
