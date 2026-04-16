import builtins
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd


def _load_module_from_path(module_path: Path):
    import importlib.util
    from uuid import uuid4

    module_name = f"ml_walkforward_report_{module_path.stem}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _as_mapping(summary):
    if summary is None:
        return None
    if isinstance(summary, Mapping):
        return dict(summary)
    if hasattr(summary, "__dict__"):
        return {key: value for key, value in vars(summary).items() if not key.startswith("_")}
    return None


def _sample_ohlcv_data(rows: int = 7) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    closes = [100.0 + idx for idx in range(rows)]
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [1_000] * rows,
        }
    )


def _get_summary(wrapper):
    candidate_names = (
        "evaluation_summary",
        "out_of_sample_summary",
        "oos_summary",
        "evaluation_report",
    )
    for name in candidate_names:
        summary = _as_mapping(getattr(wrapper, name, None))
        if summary is not None:
            return summary

    candidate_methods = (
        "get_evaluation_summary",
        "get_out_of_sample_summary",
        "build_evaluation_summary",
    )
    for name in candidate_methods:
        method = getattr(wrapper, name, None)
        if callable(method):
            summary = _as_mapping(method())
            if summary is not None:
                return summary
    return None


def test_walk_forward_ml_strategy_exposes_oos_evaluation_summary(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    class FakePrediction:
        def __init__(self, signal):
            self.signal = signal

    class FakeStrategy:
        def train(self, df):
            return 1.0

        def predict(self, df):
            return FakePrediction(1)

    monkeypatch.setattr(module, "create_ml_strategy", lambda _name: FakeStrategy(), raising=False)

    wrapper = module.WalkForwardMLStrategy("ml_rf", min_train_size=3, retrain_interval=1)
    data = _sample_ohlcv_data(rows=7)

    result = wrapper.generate_signals(data)
    summary = _get_summary(wrapper)

    assert len(result) == len(data)
    assert summary is not None
    for key in ("predictions", "evaluable", "coverage", "accuracy"):
        assert key in summary

    assert int(summary["predictions"]) == len(data) - 3
    assert int(summary["evaluable"]) <= int(summary["predictions"])
    assert 0.0 <= float(summary["coverage"]) <= 1.0
    assert 0.0 <= float(summary["accuracy"]) <= 1.0


def test_run_backtest_main_prints_walk_forward_summary(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    fake_strategy = SimpleNamespace(name="WalkForward(RandomForest)")
    fake_result = SimpleNamespace(
        total_return=1.25,
        portfolio=SimpleNamespace(total_value=1_001_250),
        max_drawdown=0.5,
        sharpe_ratio=1.1,
        trades=[],
    )
    fake_prices = [
        SimpleNamespace(
            symbol="005930",
            datetime=module.datetime.now(),
            open=100.0 + idx,
            high=101.0 + idx,
            low=99.0 + idx,
            close=100.0 + idx,
            volume=1_000,
        )
        for idx in range(7)
    ]
    fake_client = MagicMock()
    fake_client.get_daily_price_history.return_value = fake_prices

    class FakeBacktestEngine:
        def __init__(self, strategy, symbol, data, capital):
            self.strategy = strategy

        def run(self):
            self.strategy.evaluation_summary = {
                "predictions": 4,
                "evaluable": 3,
                "coverage": 0.75,
                "accuracy": 1.0,
            }
            return fake_result

    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbol="005930",
            strategy="ml_rf",
            start="20250101",
            end="20251231",
            capital=1_000_000,
            walk_forward=True,
            min_train_size=3,
            retrain_interval=1,
        ),
    )
    monkeypatch.setattr(module, "setup_logging", MagicMock())
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", MagicMock(return_value=fake_client))
    monkeypatch.setattr(module, "build_backtest_strategy", MagicMock(return_value=fake_strategy), raising=False)
    monkeypatch.setattr(module, "BacktestEngine", FakeBacktestEngine)
    print_mock = MagicMock()
    monkeypatch.setattr(builtins, "print", print_mock)

    module.main()

    printed_text = "\n".join(
        " ".join(str(arg) for arg in call.args)
        for call in print_mock.call_args_list
        if call.args
    )
    lowered = printed_text.lower()

    assert "predictions" in lowered
    assert "evaluable" in lowered
    assert "coverage" in lowered
    assert "accuracy" in lowered


def test_build_walk_forward_report_includes_symbol_and_period_metadata():
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    strategy = SimpleNamespace(
        get_evaluation_summary=lambda: {
            "predictions": 4,
            "trained_predictions": 3,
            "evaluable_predictions": 2,
            "coverage": 0.5,
            "accuracy": 1.0,
            "retrain_count": 2,
        }
    )

    report = module.build_walk_forward_report(
        strategy,
        symbol="005930",
        start="20250101",
        end="20251231",
    )

    assert report is not None
    assert report["symbol"] == "005930"
    assert report["start"] == "20250101"
    assert report["end"] == "20251231"
    assert report["predictions"] == 4


def test_print_walk_forward_summary_outputs_symbol_level_header(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    strategy = SimpleNamespace(
        get_evaluation_summary=lambda: {
            "predictions": 4,
            "trained_predictions": 3,
            "evaluable_predictions": 2,
            "coverage": 0.5,
            "accuracy": 1.0,
            "retrain_count": 2,
        }
    )
    print_mock = MagicMock()
    monkeypatch.setattr(builtins, "print", print_mock)

    module.print_walk_forward_summary(
        strategy,
        symbol="005930",
        start="20250101",
        end="20251231",
    )

    printed_text = "\n".join(
        " ".join(str(arg) for arg in call.args)
        for call in print_mock.call_args_list
        if call.args
    )

    assert "Symbol: 005930" in printed_text
    assert "Period: 20250101 ~ 20251231" in printed_text
