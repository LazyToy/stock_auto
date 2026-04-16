import builtins
import importlib
import logging
import logging.handlers
import sys
from types import ModuleType, SimpleNamespace
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


def test_run_ml_strategy_comparison_collects_target_tickers(monkeypatch):
    module = _import_run_trading_with_dummy_handlers(monkeypatch)

    def _make_trader(name, tickers):
        return SimpleNamespace(
            last_target_tickers=tickers,
            _ml_strategy=SimpleNamespace(name=name),
            dry_run=True,
        )

    monkeypatch.setattr(
        module,
        "run_single_strategy",
        MagicMock(
            side_effect=[
                _make_trader("RandomForest", ["005930", "000660"]),
                _make_trader("GradientBoosting", ["035420"]),
            ]
        ),
    )

    report = module.run_ml_strategy_comparison(
        market="KR",
        strategy_types=["ml_rf", "ml_gb"],
        dry_run=True,
        capital=1_000_000,
        is_mock=True,
    )

    rows = report["rows"]
    assert [item["strategy_type"] for item in rows] == ["ml_rf", "ml_gb"]
    assert rows[0]["strategy_name"] == "RandomForest"
    assert rows[0]["target_tickers"] == ["005930", "000660"]
    assert rows[0]["target_count"] == 2
    assert rows[1]["target_tickers"] == ["035420"]
    assert "ML Strategy Comparison (KR)" in report["text"]


def test_run_trading_main_prints_ml_comparison_report(monkeypatch):
    module = _import_run_trading_with_dummy_handlers(monkeypatch)

    printed = []
    monkeypatch.setattr(
        builtins,
        "print",
        lambda *args, **kwargs: printed.append(" ".join(map(str, args))),
    )
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            mode="single",
            market="KR",
            strategy="momentum",
            ai_filter="ml_rf",
            capital=1_000_000,
            dry_run=True,
            mock_order=False,
            real_broker=False,
            confirm_order_submission=False,
            confirm_real_broker=False,
            live=False,
            compare_ml=True,
            ml_strategies=["ml_rf", "ensemble"],
        ),
    )
    monkeypatch.setattr(
        module,
        "run_ml_strategy_comparison",
        MagicMock(
            return_value={
                "market": "KR",
                "rows": [
                    {
                        "strategy_type": "ml_rf",
                        "strategy_name": "RandomForest",
                        "order_count": 2,
                        "ordered_symbols": ["005930", "000660"],
                        "model_path": "models\\kr_ml_rf_latest.pkl",
                    },
                    {
                        "strategy_type": "ensemble",
                        "strategy_name": "Ensemble",
                        "order_count": 1,
                        "ordered_symbols": ["035420"],
                        "model_path": "models\\kr_ensemble_latest.pkl",
                    },
                ],
                "text": (
                    "ML Strategy Comparison (KR)\n"
                    "ml_rf | name=RandomForest | orders=2 | symbols=005930,000660 | model=models\\kr_ml_rf_latest.pkl\n"
                    "ensemble | name=Ensemble | orders=1 | symbols=035420 | model=models\\kr_ensemble_latest.pkl"
                ),
            }
        ),
    )

    module.main()

    assert any("ML Strategy Comparison (KR)" in line for line in printed)
    assert any("ml_rf" in line and "005930,000660" in line for line in printed)
    assert any("ensemble" in line and "035420" in line for line in printed)
