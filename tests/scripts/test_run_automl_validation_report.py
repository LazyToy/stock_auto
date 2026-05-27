import pandas as pd

from scripts import run_automl_validation_report as module
from scripts.run_automl_validation_report import build_validation_kwargs, parse_symbols


def test_parse_symbols_accepts_comma_separated_symbols():
    assert parse_symbols("AAPL, msft,005930") == ["AAPL", "MSFT", "005930"]


def test_parse_symbols_falls_back_to_single_ticker():
    assert parse_symbols("", fallback_ticker="aapl") == ["AAPL"]


def test_build_validation_kwargs_for_walk_forward():
    kwargs = build_validation_kwargs(
        validation_method="walk_forward",
        train_ratio=0.7,
        train_window=120,
        test_window=30,
        min_trades=2,
    )

    assert kwargs == {
        "train_window": 120,
        "test_window": 30,
        "min_trades": 2,
    }


def test_build_validation_kwargs_for_train_test():
    kwargs = build_validation_kwargs(
        validation_method="train_test",
        train_ratio=0.65,
        train_window=120,
        test_window=30,
        min_trades=3,
    )

    assert kwargs == {
        "train_ratio": 0.65,
        "min_trades": 3,
    }


def test_run_symbol_uses_automl_download_helper_for_kr_symbol(monkeypatch):
    calls = {}

    def fake_download(symbol, period):
        calls["symbol"] = symbol
        calls["period"] = period
        return pd.DataFrame({"Close": [100, 101, 102, 103]}), "005930.KS", None

    class FakeOptimizer:
        def __init__(self, df, **kwargs):
            calls["optimizer_df_rows"] = len(df)
            calls["optimizer_kwargs"] = kwargs

        def evolve(self, **kwargs):
            calls["evolve_kwargs"] = kwargs
            return {
                "symbol": kwargs["symbol"],
                "strategy_type": "ENSEMBLE_VOTE",
                "best_fitness": 1.0,
                "validation": {"test": {"fitness": 0.5}},
            }

    monkeypatch.setattr(module, "download_automl_price_history", fake_download)
    monkeypatch.setattr(module, "GeneticOptimizer", FakeOptimizer)

    result = module.run_symbol_optimization(
        symbol="005930",
        period="2y",
        strategy_type="ENSEMBLE_VOTE",
        fitness_metric="composite",
        population_size=4,
        generations=2,
        validation_method="train_test",
        validation_kwargs={"train_ratio": 0.7},
    )

    assert calls["symbol"] == "005930"
    assert calls["period"] == "2y"
    assert calls["evolve_kwargs"]["symbol"] == "005930.KS"
    assert result["requested_symbol"] == "005930"
    assert result["resolved_symbol"] == "005930.KS"


def test_run_symbol_records_skipped_result_when_download_fails(monkeypatch):
    monkeypatch.setattr(
        module,
        "download_automl_price_history",
        lambda symbol, period: (pd.DataFrame(), None, "No data found"),
    )

    result = module.run_symbol_optimization(
        symbol="005930",
        period="1y",
        strategy_type="ENSEMBLE_VOTE",
        fitness_metric="composite",
        population_size=4,
        generations=2,
        validation_method="walk_forward",
        validation_kwargs={"train_window": 2, "test_window": 1},
    )

    assert result == {
        "symbol": "005930",
        "requested_symbol": "005930",
        "status": "skipped",
        "error": "No data found",
    }


def test_run_symbol_records_skipped_result_when_optimizer_fails(monkeypatch):
    class FailingOptimizer:
        def __init__(self, df, **kwargs):
            pass

        def evolve(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        module,
        "download_automl_price_history",
        lambda symbol, period: (
            pd.DataFrame({"Close": [100, 101, 102, 103]}),
            "AAPL",
            None,
        ),
    )
    monkeypatch.setattr(module, "GeneticOptimizer", FailingOptimizer)

    result = module.run_symbol_optimization(
        symbol="AAPL",
        period="1y",
        strategy_type="ENSEMBLE_VOTE",
        fitness_metric="composite",
        population_size=4,
        generations=2,
        validation_method="walk_forward",
        validation_kwargs={"train_window": 2, "test_window": 1},
    )

    assert result == {
        "symbol": "AAPL",
        "requested_symbol": "AAPL",
        "resolved_symbol": "AAPL",
        "status": "skipped",
        "error": "boom",
    }
