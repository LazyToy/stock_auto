import pandas as pd

from scripts import run_signal_monitor as module


def test_parse_symbols_accepts_csv_and_deduplicates():
    assert module.parse_symbols("aapl, MSFT, aapl") == ["AAPL", "MSFT"]


def test_load_watchlist_prefers_explicit_symbols():
    class Config:
        def get_symbols(self, market):
            return ["005930"]

    assert module.load_watchlist("AAPL", market="us", config_loader=Config()) == ["AAPL"]


def test_load_watchlist_reads_config_when_symbols_omitted():
    class Config:
        def get_symbols(self, market):
            assert market == "korea"
            return ["005930", "000660"]

    assert module.load_watchlist("", market="korea", config_loader=Config()) == ["005930", "000660"]


def test_run_signal_monitor_once_uses_artifacts_and_notifier(tmp_path):
    messages = []
    artifact = {
        "requested_symbol": "005930",
        "resolved_symbol": "005930.KS",
        "strategy_type": "RESILIENT_RECLAIM",
        "best_params": [4, 2, 3, 9800, 100, 9700],
        "best_fitness": 1.2,
        "validation": {"test": {"fitness": 0.8}},
    }
    frame = pd.DataFrame(
        {
            "High": [101, 111, 107, 105, 113],
            "Low": [99, 109, 105, 103, 111],
            "Close": [100, 110, 106, 104, 112],
            "Volume": 1000,
        },
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )

    results = module.run_signal_monitor_once(
        symbols=["005930"],
        artifacts_dir=tmp_path / "params",
        period="6mo",
        state_path=tmp_path / "state.json",
        artifact_loader=lambda path: [artifact],
        history_fetcher=lambda symbol, period: frame,
        notifier=messages.append,
    )

    assert len(results) == 1
    assert results[0].signal.action == "BUY"
    assert len(messages) == 1


def test_run_signal_monitor_loop_can_run_limited_iterations(monkeypatch):
    calls = []

    monkeypatch.setattr(
        module,
        "run_signal_monitor_once",
        lambda **kwargs: calls.append(kwargs) or [],
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    module.run_signal_monitor_loop(
        symbols=["AAPL"],
        artifacts_dir="data/automl_params",
        period="1y",
        state_path="data/state.json",
        interval_seconds=1,
        iterations=2,
    )

    assert len(calls) == 2
