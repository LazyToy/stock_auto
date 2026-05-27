import json

import pandas as pd

from src.monitoring.signal_monitor import (
    AutomlSignalMonitor,
    SignalAlertStateStore,
    build_signal_state_key,
    format_automl_signal_message,
)


def _reclaim_frame():
    return pd.DataFrame(
        {
            "High": [101, 111, 107, 105, 113],
            "Low": [99, 109, 105, 103, 111],
            "Close": [100, 110, 106, 104, 112],
            "Volume": 1000,
        },
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )


def test_signal_monitor_dispatches_latest_resilient_reclaim_buy_once():
    sent_messages = []
    fetched_symbols = []
    artifact = {
        "requested_symbol": "005930",
        "resolved_symbol": "005930.KS",
        "strategy_type": "RESILIENT_RECLAIM",
        "strategy_display_name": "Resilient Reclaim",
        "best_params": [4, 2, 3, 9800, 100, 9700],
        "best_fitness": 1.2,
        "validation": {
            "test": {"fitness": 0.8},
            "overfit_guard": {"passes": True},
        },
    }

    def fetch_history(symbol, period):
        fetched_symbols.append((symbol, period))
        return _reclaim_frame()

    monitor = AutomlSignalMonitor(
        [artifact],
        history_fetcher=fetch_history,
        notifier=sent_messages.append,
        period="6mo",
    )

    first = monitor.scan_once(["005930"])
    second = monitor.scan_once(["005930"])

    assert fetched_symbols == [("005930.KS", "6mo"), ("005930.KS", "6mo")]
    assert len(first) == 1
    assert first[0].signal.action == "BUY"
    assert first[0].signal.symbol == "005930"
    assert first[0].signal.resolved_symbol == "005930.KS"
    assert first[0].sent is True
    assert len(sent_messages) == 1
    assert "advisory only" in sent_messages[0]
    assert second == []


def test_signal_monitor_dispatches_sell_signal_from_existing_strategy():
    messages = []
    artifact = {
        "symbol": "AAPL",
        "strategy_type": "MA_CROSSOVER",
        "best_params": [1, 2],
        "validation": {"overfit_guard": {"passes": True}},
    }
    frame = pd.DataFrame(
        {
            "High": [101, 102, 100],
            "Low": [99, 100, 98],
            "Close": [100, 101, 99],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )

    monitor = AutomlSignalMonitor(
        [artifact],
        history_fetcher=lambda symbol, period: frame,
        notifier=messages.append,
    )

    results = monitor.scan_once(["AAPL"])

    assert len(results) == 1
    assert results[0].signal.action == "SELL"
    assert "SELL AAPL" in messages[0]


def test_signal_monitor_skips_failed_overfit_guard_artifacts():
    artifact = {
        "symbol": "AAPL",
        "strategy_type": "MA_CROSSOVER",
        "best_params": [1, 2],
        "validation": {"overfit_guard": {"passes": False}},
    }
    monitor = AutomlSignalMonitor(
        [artifact],
        history_fetcher=lambda symbol, period: _reclaim_frame(),
        notifier=lambda message: True,
    )

    assert monitor.scan_once(["AAPL"]) == []


def test_signal_monitor_catches_notifier_exception_without_marking_state():
    artifact = {
        "requested_symbol": "005930",
        "resolved_symbol": "005930.KS",
        "strategy_type": "RESILIENT_RECLAIM",
        "best_params": [4, 2, 3, 9800, 100, 9700],
        "validation": {"overfit_guard": {"passes": True}},
    }

    def raising_notifier(message):
        raise RuntimeError("provider boom")

    monitor = AutomlSignalMonitor(
        [artifact],
        history_fetcher=lambda symbol, period: _reclaim_frame(),
        notifier=raising_notifier,
    )

    results = monitor.scan_once(["005930"])

    assert len(results) == 1
    assert results[0].sent is False
    assert results[0].reason == "notifier_failed"
    assert monitor.state == set()


def test_signal_alert_state_store_persists_without_exposing_secrets(tmp_path):
    path = tmp_path / "state.json"
    store = SignalAlertStateStore(path)
    state_key = "AAPL:MA_CROSSOVER:2024-01-03:SELL"

    assert store.load() == set()
    assert store.save({state_key}) is True

    assert store.load() == {state_key}
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"automl_signal_alerts": [state_key]}


def test_format_automl_signal_message_is_advisory_only():
    monitor = AutomlSignalMonitor(
        [],
        history_fetcher=lambda symbol, period: pd.DataFrame(),
        notifier=lambda message: True,
    )
    signal = monitor.build_signal(
        "AAPL",
        {
            "symbol": "AAPL",
            "strategy_type": "MA_CROSSOVER",
            "best_params": [1, 2],
            "best_fitness": 1.0,
        },
        pd.DataFrame(
            {
                "High": [101, 102, 100],
                "Low": [99, 100, 98],
                "Close": [100, 101, 99],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        ),
    )

    assert signal is not None
    message = format_automl_signal_message(signal)

    assert build_signal_state_key(signal) == "AAPL:MA_CROSSOVER:2024-01-03 00:00:00:SELL"
    assert "AutoML Signal" in message
    assert "advisory only" in message
