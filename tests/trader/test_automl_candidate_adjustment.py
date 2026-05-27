import importlib
import logging
import logging.handlers
import sys
from pathlib import Path

import pandas as pd


class _DummyHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return


def _import_auto_trader_with_dummy_handlers(monkeypatch):
    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", _DummyHandler)
    sys.modules.pop("src.trader.auto_trader", None)
    return importlib.import_module("src.trader.auto_trader")


def test_build_automl_trading_config_defaults_to_disabled(monkeypatch):
    module = _import_auto_trader_with_dummy_handlers(monkeypatch)

    config = module.build_automl_trading_config(None)

    assert config.enabled is False
    assert config.mode == "advisory"


def test_automl_candidate_adjustment_applies_only_in_score_bonus_mode(monkeypatch, tmp_path):
    module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    artifact_dir = tmp_path / "automl_params"
    artifact_dir.mkdir()
    (artifact_dir / "AAPL_macd_rsi.json").write_text(
        """
        {
          "symbol": "AAPL",
          "strategy_type": "MACD_RSI",
          "best_fitness": 2.0,
          "validation": {"test": {"fitness": 1.0}}
        }
        """,
        encoding="utf-8",
    )

    trader = object.__new__(module.AutoTrader)
    trader.automl_config = module.build_automl_trading_config(
        {
            "enabled": True,
            "mode": "score_bonus",
            "params_path": str(artifact_dir),
            "min_fitness": 0.5,
            "max_bonus": 0.2,
        }
    )

    candidates = pd.DataFrame([{"ticker": "AAPL", "score": 1.0}])
    adjusted = trader._apply_automl_candidate_adjustment(candidates)

    assert adjusted.loc[0, "score"] == 1.2
    assert adjusted.loc[0, "automl_strategy"] == "MACD_RSI"


def test_automl_advisory_mode_records_metadata_without_bonus(monkeypatch, tmp_path):
    module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    artifact_dir = tmp_path / "automl_params"
    artifact_dir.mkdir()
    (artifact_dir / "AAPL_macd_rsi.json").write_text(
        '{"symbol": "AAPL", "strategy_type": "MACD_RSI", "best_fitness": 2.0}',
        encoding="utf-8",
    )

    trader = object.__new__(module.AutoTrader)
    trader.automl_config = module.build_automl_trading_config(
        {
            "enabled": True,
            "mode": "advisory",
            "params_path": str(artifact_dir),
            "min_fitness": 0.5,
            "max_bonus": 0.2,
        }
    )

    candidates = pd.DataFrame([{"ticker": "AAPL", "score": 1.0}])
    adjusted = trader._apply_automl_candidate_adjustment(candidates)

    assert adjusted.loc[0, "score"] == 1.0
    assert adjusted.loc[0, "automl_strategy"] == "MACD_RSI"
