import importlib
import logging
import logging.handlers
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock


class _DummyHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return


def _import_run_trading_with_dummy_handlers(monkeypatch):
    auto_trader_stub = ModuleType("src.trader.auto_trader")
    auto_trader_stub.AutoTrader = type("AutoTrader", (), {})

    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging, "FileHandler", _DummyHandler)
    monkeypatch.setitem(sys.modules, "src.trader.auto_trader", auto_trader_stub)
    sys.modules.pop("scripts.run_trading", None)
    return importlib.import_module("scripts.run_trading")


def _write_model(path: Path, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("placeholder", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _workspace_tmp_dir(test_name: str) -> Path:
    root = Path.cwd() / ".test-artifacts" / "run_trading_ml_runtime" / test_name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_run_single_strategy_loads_latest_saved_ml_model_for_runtime_strategy(monkeypatch):
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    strategy = MagicMock()
    strategy.name = "RuntimeML"
    trader = MagicMock()
    tmp_dir = _workspace_tmp_dir("loads_latest")
    newer_model = tmp_dir / "models" / "kr_ml_rf_202502.pkl"
    _write_model(tmp_dir / "models" / "kr_ml_rf_202501.pkl", 1_700_000_000)
    _write_model(newer_model, 1_800_000_000)
    _write_model(tmp_dir / "models" / "us_ml_rf_202503.pkl", 1_900_000_000)
    _write_model(tmp_dir / "models" / "kr_ml_gb_202503.pkl", 1_900_000_000)

    monkeypatch.setattr(run_trading_module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(run_trading_module, "ML_AVAILABLE", True)
    monkeypatch.setattr(run_trading_module.Config, "BASE_DIR", tmp_dir)
    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(run_trading_module, "AutoTrader", MagicMock(return_value=trader))
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=strategy))

    run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=True,
        is_mock=True,
    )

    strategy.load_model.assert_called_once_with(str(newer_model))
    trader.set_ml_strategy.assert_called_once_with(strategy)
    trader.run_rebalancing.assert_called_once_with()


def test_run_single_strategy_skips_model_load_when_no_saved_model_exists(monkeypatch):
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    strategy = MagicMock()
    strategy.name = "RuntimeML"
    trader = MagicMock()
    tmp_dir = _workspace_tmp_dir("skips_when_missing")

    monkeypatch.setattr(run_trading_module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(run_trading_module, "ML_AVAILABLE", True)
    monkeypatch.setattr(run_trading_module.Config, "BASE_DIR", tmp_dir)
    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(run_trading_module, "AutoTrader", MagicMock(return_value=trader))
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=strategy))

    run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=True,
        is_mock=True,
    )

    strategy.load_model.assert_not_called()
    trader.set_ml_strategy.assert_called_once_with(strategy)
    trader.run_rebalancing.assert_called_once_with()


def test_run_single_strategy_continues_when_saved_ml_model_load_fails(monkeypatch):
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    strategy = MagicMock()
    strategy.name = "RuntimeML"
    strategy.load_model.side_effect = RuntimeError("corrupt model")
    trader = MagicMock()
    tmp_dir = _workspace_tmp_dir("continues_on_load_failure")
    model_path = tmp_dir / "models" / "kr_ml_rf_202502.pkl"
    _write_model(model_path, 1_800_000_000)

    monkeypatch.setattr(run_trading_module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(run_trading_module, "ML_AVAILABLE", True)
    monkeypatch.setattr(run_trading_module.Config, "BASE_DIR", tmp_dir)
    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(run_trading_module, "AutoTrader", MagicMock(return_value=trader))
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=strategy))

    run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=True,
        is_mock=True,
    )

    strategy.load_model.assert_called_once_with(str(model_path))
    trader.set_ml_strategy.assert_called_once_with(strategy)
    trader.run_rebalancing.assert_called_once_with()
