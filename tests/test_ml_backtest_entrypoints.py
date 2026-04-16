import builtins
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def _load_module_from_path(module_path: Path):
    import importlib.util
    from uuid import uuid4

    module_name = f"ml_entrypoint_{module_path.stem}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_backtest_builds_walk_forward_ml_strategy(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    monkeypatch.setattr(module, "build_indicator_strategy", MagicMock())
    monkeypatch.setattr(module, "ML_STRATEGY_AVAILABLE", True, raising=False)
    data = module.pd.DataFrame(
        {
            "datetime": module.pd.date_range("2024-01-01", periods=30, freq="D"),
            "open": [1.0] * 30,
            "high": [1.0] * 30,
            "low": [1.0] * 30,
            "close": [1.0] * 30,
            "volume": [1] * 30,
        }
    )

    strategy = module.build_backtest_strategy("ml_rf", data)

    assert strategy.__class__.__name__ == "WalkForwardMLStrategy"
    assert strategy.name == "WalkForward(RandomForest)"


def test_walk_forward_ml_strategy_trains_only_on_past_data(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    created = []

    class FakePrediction:
        def __init__(self, signal):
            self.signal = signal

    class FakeStrategy:
        name = "RandomForest"

        def __init__(self):
            self.train_lengths = []
            self.predict_lengths = []

        def train(self, df):
            self.train_lengths.append(len(df))
            return 1.0

        def predict(self, df):
            self.predict_lengths.append(len(df))
            return FakePrediction(1)

    def _create_strategy(_name):
        strategy = FakeStrategy()
        created.append(strategy)
        return strategy

    monkeypatch.setattr(module, "create_ml_strategy", _create_strategy, raising=False)
    wrapper = module.WalkForwardMLStrategy("ml_rf", min_train_size=3, retrain_interval=2)
    data = module.pd.DataFrame(
        {
            "datetime": module.pd.date_range("2024-01-01", periods=7, freq="D"),
            "open": [1.0] * 7,
            "high": [1.0] * 7,
            "low": [1.0] * 7,
            "close": [1.0] * 7,
            "volume": [1] * 7,
        }
    )

    result = wrapper.generate_signals(data)

    assert result["signal"].tolist() == [0, 0, 0, 1, 1, 1, 1]
    assert [strategy.train_lengths for strategy in created] == [[3], [5]]
    assert created[0].predict_lengths == [4, 5]
    assert created[1].predict_lengths == [6, 7]


def test_walk_forward_ml_strategy_exposes_out_of_sample_summary(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    class FakePrediction:
        def __init__(self, signal):
            self.signal = signal

    class FakeStrategy:
        name = "RandomForest"

        def train(self, df):
            return 1.0

        def predict(self, df):
            return FakePrediction(1)

    monkeypatch.setattr(
        module,
        "create_ml_strategy",
        lambda _name: FakeStrategy(),
        raising=False,
    )

    wrapper = module.WalkForwardMLStrategy(
        "ml_rf",
        min_train_size=3,
        retrain_interval=10,
        symbol="005930",
    )
    data = module.pd.DataFrame(
        {
            "datetime": module.pd.date_range("2024-01-01", periods=12, freq="D"),
            "open": [float(value) for value in range(100, 112)],
            "high": [float(value) for value in range(101, 113)],
            "low": [float(value) for value in range(99, 111)],
            "close": [float(value) for value in range(100, 112)],
            "volume": [1_000] * 12,
        }
    )

    wrapper.generate_signals(data)
    summary = wrapper.get_evaluation_summary()

    assert summary["symbol"] == "005930"
    assert summary["predictions"] == 9
    assert summary["evaluable_predictions"] == 4
    assert summary["coverage"] == 4 / 9
    assert summary["accuracy"] == 1.0


def test_walk_forward_summary_excludes_untrained_predictions(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    class FakePrediction:
        def __init__(self, signal):
            self.signal = signal

    class FakeStrategy:
        name = "RandomForest"

        def __init__(self):
            self.is_trained = False

        def train(self, df):
            self.is_trained = len(df) >= 5
            return 1.0 if self.is_trained else 0.0

        def predict(self, df):
            return FakePrediction(1 if self.is_trained else 0)

    monkeypatch.setattr(module, "create_ml_strategy", lambda _name: FakeStrategy(), raising=False)

    wrapper = module.WalkForwardMLStrategy("ml_rf", min_train_size=3, retrain_interval=1)
    data = module.pd.DataFrame(
        {
            "datetime": module.pd.date_range("2024-01-01", periods=12, freq="D"),
            "open": [float(value) for value in range(100, 112)],
            "high": [float(value) for value in range(101, 113)],
            "low": [float(value) for value in range(99, 111)],
            "close": [float(value) for value in range(100, 112)],
            "volume": [1_000] * 12,
        }
    )

    wrapper.generate_signals(data)
    summary = wrapper.get_evaluation_summary()

    assert summary["predictions"] == 9
    assert summary["trained_predictions"] == 7
    assert summary["evaluable_predictions"] == 2
    assert summary["retrain_count"] == 9
    assert summary["coverage"] == 2 / 9
    assert summary["accuracy"] == 1.0


def test_run_backtest_main_supports_ml_strategy(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    fake_strategy = MagicMock()
    fake_strategy.name = "RandomForest"
    fake_client = MagicMock()
    fake_client.get_daily_price_history.return_value = [
        SimpleNamespace(
            symbol="005930",
            datetime=module.datetime.now(),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
        )
        for _ in range(40)
    ]
    fake_result = MagicMock(
        total_return=1.0,
        portfolio=MagicMock(total_value=10001000),
        max_drawdown=0.1,
        sharpe_ratio=1.0,
        trades=[],
    )

    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbol="005930",
            strategy="ml_rf",
            start="20250101",
            end="20251231",
            capital=1_000_000,
        ),
    )
    monkeypatch.setattr(module, "setup_logging", MagicMock())
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", MagicMock(return_value=fake_client))
    monkeypatch.setattr(module, "build_backtest_strategy", MagicMock(return_value=fake_strategy), raising=False)
    monkeypatch.setattr(module, "BacktestEngine", MagicMock(return_value=MagicMock(run=MagicMock(return_value=fake_result))))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    module.main()

    module.build_backtest_strategy.assert_called_once()


def test_run_backtest_main_prints_walk_forward_evaluation_summary(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    fake_strategy = MagicMock()
    fake_strategy.name = "WalkForward(RandomForest)"
    fake_strategy.get_evaluation_summary.return_value = {
        "symbol": "005930",
        "predictions": 12,
        "trained_predictions": 9,
        "evaluable_predictions": 8,
        "coverage": 8 / 12,
        "accuracy": 0.75,
        "retrain_count": 3,
    }
    fake_client = MagicMock()
    fake_client.get_daily_price_history.return_value = [
        SimpleNamespace(
            symbol="005930",
            datetime=module.datetime.now(),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
        )
        for _ in range(40)
    ]
    fake_result = MagicMock(
        total_return=1.0,
        portfolio=MagicMock(total_value=10001000),
        max_drawdown=0.1,
        sharpe_ratio=1.0,
        trades=[],
    )
    printed = []

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
            min_train_size=120,
            retrain_interval=1,
        ),
    )
    monkeypatch.setattr(module, "setup_logging", MagicMock())
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", MagicMock(return_value=fake_client))
    monkeypatch.setattr(module, "build_backtest_strategy", MagicMock(return_value=fake_strategy), raising=False)
    monkeypatch.setattr(
        module,
        "BacktestEngine",
        MagicMock(return_value=MagicMock(run=MagicMock(return_value=fake_result))),
    )
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(map(str, args))))

    module.main()

    assert any("Walk-forward evaluation" in line for line in printed)
    assert any("Symbol: 005930" in line for line in printed)
    assert any("Predictions: 12" in line for line in printed)
    assert any("Trained predictions: 9" in line for line in printed)
    assert any("Retrain count: 3" in line for line in printed)
    assert any("Accuracy: 0.75" in line for line in printed)
