from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from src.data.models import Account, Order, OrderSide, OrderType
from src.trader.self_healing import OrderContext, SelfHealingEngine


def _import_auto_trader_with_dummy_handlers(monkeypatch):
    import importlib
    import logging
    import logging.handlers
    import sys

    class _DummyHandler(logging.Handler):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def emit(self, record):
            return

    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", _DummyHandler)
    sys.modules.pop("src.trader.auto_trader", None)
    return importlib.import_module("src.trader.auto_trader")


def _import_run_trading_with_dummy_handlers(monkeypatch):
    import importlib
    import logging
    import logging.handlers
    import sys

    class _DummyHandler(logging.Handler):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def emit(self, record):
            return

    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging, "FileHandler", _DummyHandler)
    sys.modules.pop("scripts.run_trading", None)
    return importlib.import_module("scripts.run_trading")


def test_auto_trader_run_rebalancing_submits_buy_via_broker(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader

    broker = MagicMock()
    api_client = MagicMock()
    api_client.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )

    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())

    trader = AutoTrader(
        api_client=api_client,
        broker=broker,
        universe=["005930"],
        max_stocks=1,
        dry_run=False,
        market="KR",
    )
    trader.export_dashboard_state = MagicMock()
    trader._process_exit_strategies = MagicMock(return_value=[])
    trader.selector.calculate_metrics = MagicMock(
        return_value=pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                }
            ]
        )
    )

    trader.run_rebalancing()

    broker.place_order.assert_called_once()
    api_client.place_order.assert_not_called()
    order_arg = broker.place_order.call_args.args[0]
    assert isinstance(order_arg, Order)
    assert order_arg.symbol == "005930"
    assert order_arg.side == OrderSide.BUY
    assert order_arg.order_type == OrderType.MARKET


def test_run_single_strategy_submits_broker_order_and_records_trade(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    fake_db = MagicMock()
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )
    broker = MagicMock()
    broker.place_order.return_value = "ORD-RUN-1"

    monkeypatch.setattr(auto_trader_module, "get_db", MagicMock(return_value=fake_db))
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "export_dashboard_state",
        lambda self, balance=None: None,
    )
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "_process_exit_strategies",
        lambda self, account, current_scores: [],
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "calculate_metrics",
        lambda self: pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                }
            ]
        ),
    )

    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930"]})
    build_client = MagicMock(return_value=mock_api)
    build_broker = MagicMock(return_value=broker)
    monkeypatch.setattr(run_trading_module, "build_kis_client", build_client)
    monkeypatch.setattr(run_trading_module, "build_kis_broker", build_broker)

    trader = run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="momentum",
        dry_run=False,
        is_mock=True,
    )

    assert isinstance(trader, auto_trader_module.AutoTrader)
    build_client.assert_called_once_with(
        market="KR",
        is_mock=True,
        client_cls=run_trading_module.KISAPIClient,
    )
    build_broker.assert_called_once_with(
        market="KR",
        is_mock=True,
        broker_cls=run_trading_module.KISBroker,
    )
    broker.place_order.assert_called_once()
    mock_api.place_order.assert_not_called()
    order_arg = broker.place_order.call_args.args[0]
    assert isinstance(order_arg, Order)
    assert order_arg.symbol == "005930"
    assert order_arg.side == OrderSide.BUY
    assert order_arg.order_type == OrderType.MARKET
    assert order_arg.price == 0
    assert broker.place_order.call_args.kwargs["exchange"] == "KR"
    fake_db.insert_trade.assert_called_once()
    trade_record = fake_db.insert_trade.call_args.args[0]
    assert trade_record.symbol == "005930"
    assert trade_record.side == "BUY"
    assert trade_record.market == "KR"


def test_run_single_strategy_applies_ml_filter_before_mock_broker_order(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    fake_db = MagicMock()
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )
    broker = MagicMock()
    broker.place_order.return_value = "ORD-ML-1"

    class FakeMLStrategy:
        name = "FakeMLStrategy"
        is_trained = True

        def predict(self, df):
            assert list(df["ticker"]) == ["005930", "000660"]
            return [-1, 1]

    monkeypatch.setattr(auto_trader_module, "get_db", MagicMock(return_value=fake_db))
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "export_dashboard_state",
        lambda self, balance=None: None,
    )
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "_process_exit_strategies",
        lambda self, account, current_scores: [],
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "calculate_metrics",
        lambda self: pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                },
                {
                    "ticker": "000660",
                    "score": 1.5,
                    "current_price": 80_000.0,
                    "exchange": "KR",
                },
            ]
        ),
    )

    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930", "000660"]})
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=FakeMLStrategy()))
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=mock_api))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=broker))

    trader = run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=False,
        is_mock=True,
    )

    assert isinstance(trader, auto_trader_module.AutoTrader)
    run_trading_module.StrategyFactory.create.assert_called_once_with("ml_rf")
    broker.place_order.assert_called_once()
    mock_api.place_order.assert_not_called()
    order_arg = broker.place_order.call_args.args[0]
    assert isinstance(order_arg, Order)
    assert order_arg.symbol == "000660"
    assert order_arg.side == OrderSide.BUY
    assert order_arg.order_type == OrderType.MARKET
    assert order_arg.price == 0
    assert broker.place_order.call_args.kwargs["exchange"] == "KR"
    fake_db.insert_trade.assert_called_once()
    trade_record = fake_db.insert_trade.call_args.args[0]
    assert trade_record.symbol == "000660"
    assert trade_record.side == "BUY"
    assert trade_record.market == "KR"


def test_run_single_strategy_applies_ml_prediction_style_filter(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    fake_db = MagicMock()
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )
    broker = MagicMock()
    broker.place_order.return_value = "ORD-ML-PRED-1"

    from src.strategies.ml_strategy import MLPrediction

    class FakeMLStrategy:
        name = "FakeMLPredictionStrategy"
        is_trained = True

        def train(self, df):
            raise AssertionError("runtime ML path should not retrain per symbol")

        def predict(self, df):
            if "ticker" in df.columns:
                raise TypeError("expects per-symbol OHLCV frame")
            signal = 1 if float(df["close"].iloc[-1]) >= 20.0 else -1
            return MLPrediction(signal, 0.8, [], self.name, datetime.now().isoformat())

    monkeypatch.setattr(auto_trader_module, "get_db", MagicMock(return_value=fake_db))
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "export_dashboard_state",
        lambda self, balance=None: None,
    )
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "_process_exit_strategies",
        lambda self, account, current_scores: [],
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "calculate_metrics",
        lambda self: pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                },
                {
                    "ticker": "000660",
                    "score": 1.5,
                    "current_price": 80_000.0,
                    "exchange": "KR",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "download_data",
        lambda self: self.data.update(
            {
                "005930": pd.DataFrame(
                    {
                        "symbol": ["005930"] * 6,
                        "open": [10.0] * 6,
                        "high": [11.0] * 6,
                        "low": [9.0] * 6,
                        "close": [10.0] * 6,
                        "volume": [1_000] * 6,
                    }
                ),
                "000660": pd.DataFrame(
                    {
                        "symbol": ["000660"] * 6,
                        "open": [20.0] * 6,
                        "high": [21.0] * 6,
                        "low": [19.0] * 6,
                        "close": [20.0] * 6,
                        "volume": [1_000] * 6,
                    }
                ),
            }
        ),
    )

    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930", "000660"]})
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=FakeMLStrategy()))
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=mock_api))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=broker))

    trader = run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=False,
        is_mock=True,
    )

    assert isinstance(trader, auto_trader_module.AutoTrader)
    broker.place_order.assert_called_once()
    order_arg = broker.place_order.call_args.args[0]
    assert isinstance(order_arg, Order)
    assert order_arg.symbol == "000660"
    assert broker.place_order.call_args.kwargs["exchange"] == "KR"
    fake_db.insert_trade.assert_called_once()


def test_run_single_strategy_uses_loaded_ml_model_without_per_symbol_retraining(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    fake_db = MagicMock()
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )
    broker = MagicMock()
    broker.place_order.return_value = "ORD-ML-LOADED-1"

    from src.strategies.ml_strategy import MLPrediction

    class FakeMLStrategy:
        name = "LoadedMLStrategy"
        is_trained = False

        def load_model(self, path):
            self.is_trained = True
            self.loaded_path = path

        def train(self, df):
            raise AssertionError("loaded runtime model should not retrain per symbol")

        def predict(self, df):
            if "ticker" in df.columns:
                raise TypeError("expects per-symbol OHLCV frame")
            signal = 1 if float(df["close"].iloc[-1]) >= 20.0 else -1
            return MLPrediction(signal, 0.8, [], self.name, datetime.now().isoformat())

    monkeypatch.setattr(auto_trader_module, "get_db", MagicMock(return_value=fake_db))
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "export_dashboard_state",
        lambda self, balance=None: None,
    )
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "_process_exit_strategies",
        lambda self, account, current_scores: [],
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "calculate_metrics",
        lambda self: pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                },
                {
                    "ticker": "000660",
                    "score": 1.5,
                    "current_price": 80_000.0,
                    "exchange": "KR",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "download_data",
        lambda self: self.data.update(
            {
                "005930": pd.DataFrame(
                    {
                        "symbol": ["005930"] * 6,
                        "open": [10.0] * 6,
                        "high": [11.0] * 6,
                        "low": [9.0] * 6,
                        "close": [10.0] * 6,
                        "volume": [1_000] * 6,
                    }
                ),
                "000660": pd.DataFrame(
                    {
                        "symbol": ["000660"] * 6,
                        "open": [20.0] * 6,
                        "high": [21.0] * 6,
                        "low": [19.0] * 6,
                        "close": [20.0] * 6,
                        "volume": [1_000] * 6,
                    }
                ),
            }
        ),
    )

    fake_strategy = FakeMLStrategy()
    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930", "000660"]})
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=fake_strategy))
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=mock_api))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=broker))
    monkeypatch.setattr(
        run_trading_module,
        "_find_latest_runtime_model_path",
        MagicMock(return_value=Path("models/kr_ml_rf_202603.pkl")),
    )

    trader = run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=False,
        is_mock=True,
    )

    assert isinstance(trader, auto_trader_module.AutoTrader)
    assert fake_strategy.loaded_path == "models\\kr_ml_rf_202603.pkl"
    broker.place_order.assert_called_once()
    order_arg = broker.place_order.call_args.args[0]
    assert isinstance(order_arg, Order)
    assert order_arg.symbol == "000660"
    assert broker.place_order.call_args.kwargs["exchange"] == "KR"
    fake_db.insert_trade.assert_called_once()


def test_run_single_strategy_falls_back_to_selector_when_runtime_model_load_fails(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    fake_db = MagicMock()
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )
    broker = MagicMock()
    broker.place_order.return_value = "ORD-ML-FALLBACK-1"

    class FakeMLStrategy:
        name = "BrokenLoadedMLStrategy"
        is_trained = False

        def load_model(self, path):
            raise RuntimeError("corrupt model")

        def train(self, df):
            raise AssertionError("runtime ML path should not retrain after load failure")

        def predict(self, df):
            raise RuntimeError("untrained runtime model should fall back to selector")

    monkeypatch.setattr(auto_trader_module, "get_db", MagicMock(return_value=fake_db))
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "export_dashboard_state",
        lambda self, balance=None: None,
    )
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "_process_exit_strategies",
        lambda self, account, current_scores: [],
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "calculate_metrics",
        lambda self: pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                }
            ]
        ),
    )

    fake_strategy = FakeMLStrategy()
    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(run_trading_module.StrategyFactory, "create", MagicMock(return_value=fake_strategy))
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=mock_api))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=broker))
    monkeypatch.setattr(
        run_trading_module,
        "_find_latest_runtime_model_path",
        MagicMock(return_value=Path("models/kr_ml_rf_202603.pkl")),
    )

    trader = run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=False,
        is_mock=True,
    )

    assert isinstance(trader, auto_trader_module.AutoTrader)
    broker.place_order.assert_called_once()
    order_arg = broker.place_order.call_args.args[0]
    assert isinstance(order_arg, Order)
    assert order_arg.symbol == "005930"
    assert broker.place_order.call_args.kwargs["exchange"] == "KR"
    fake_db.insert_trade.assert_called_once()


def test_run_single_strategy_does_not_record_trade_when_broker_order_fails(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    fake_db = MagicMock()
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[],
    )
    broker = MagicMock()
    broker.place_order.side_effect = RuntimeError("order failed")

    monkeypatch.setattr(auto_trader_module, "get_db", MagicMock(return_value=fake_db))
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "export_dashboard_state",
        lambda self, balance=None: None,
    )
    monkeypatch.setattr(
        auto_trader_module.AutoTrader,
        "_process_exit_strategies",
        lambda self, account, current_scores: [],
    )
    monkeypatch.setattr(
        auto_trader_module.StockSelector,
        "calculate_metrics",
        lambda self: pd.DataFrame(
            [
                {
                    "ticker": "005930",
                    "score": 2.0,
                    "current_price": 50_000.0,
                    "exchange": "KR",
                }
            ]
        ),
    )

    monkeypatch.setattr(run_trading_module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(run_trading_module, "build_kis_client", MagicMock(return_value=mock_api))
    monkeypatch.setattr(run_trading_module, "build_kis_broker", MagicMock(return_value=broker))

    trader = run_trading_module.run_single_strategy(
        market="KR",
        strategy_type="momentum",
        dry_run=False,
        is_mock=True,
    )

    assert isinstance(trader, auto_trader_module.AutoTrader)
    broker.place_order.assert_called_once()
    fake_db.insert_trade.assert_not_called()


def test_run_ml_strategy_comparison_formats_mock_report(monkeypatch):
    run_trading_module = _import_run_trading_with_dummy_handlers(monkeypatch)

    captured_calls = []
    reports = {
        "ml_rf": {
            "strategy_type": "ml_rf",
            "strategy_name": "RandomForest",
            "order_count": 1,
            "ordered_symbols": ["005930"],
            "model_path": "models\\kr_ml_rf_latest.pkl",
        },
        "ml_gb": {
            "strategy_type": "ml_gb",
            "strategy_name": "GradientBoosting",
            "order_count": 0,
            "ordered_symbols": [],
            "model_path": None,
        },
        "ensemble": {
            "strategy_type": "ensemble",
            "strategy_name": "Ensemble",
            "order_count": 2,
            "ordered_symbols": ["005930", "000660"],
            "model_path": "models\\kr_ensemble_latest.pkl",
        },
    }

    def fake_run_single_strategy(*, market, strategy_type, dry_run, capital, is_mock):
        captured_calls.append(
            {
                "market": market,
                "strategy_type": strategy_type,
                "dry_run": dry_run,
                "capital": capital,
                "is_mock": is_mock,
            }
        )
        return SimpleNamespace(comparison_report=reports[strategy_type])

    monkeypatch.setattr(run_trading_module, "run_single_strategy", fake_run_single_strategy)

    result = run_trading_module.run_ml_strategy_comparison(
        market="KR",
        dry_run=False,
        capital=2_500_000,
        is_mock=True,
    )

    assert [call["strategy_type"] for call in captured_calls] == ["ml_rf", "ml_gb", "ensemble"]
    assert all(call["market"] == "KR" for call in captured_calls)
    assert all(call["dry_run"] is False for call in captured_calls)
    assert all(call["capital"] == 2_500_000 for call in captured_calls)
    assert all(call["is_mock"] is True for call in captured_calls)
    assert result["rows"] == [reports["ml_rf"], reports["ml_gb"], reports["ensemble"]]
    assert "ML Strategy Comparison (KR)" in result["text"]
    assert "ml_rf" in result["text"]
    assert "orders=1" in result["text"]
    assert "symbols=005930" in result["text"]
    assert "model=models\\kr_ml_rf_latest.pkl" in result["text"]
    assert "ensemble" in result["text"]
    assert "symbols=005930,000660" in result["text"]


def test_self_healing_execute_order_uses_broker_recovery_path(monkeypatch):
    broker = MagicMock()
    broker.place_order.return_value = "ORD-BROKER-1"

    engine = SelfHealingEngine(api_client=None, broker=broker)
    monkeypatch.setattr(engine, "_monitor_order", lambda context: False)

    context = OrderContext(
        symbol="IBM",
        quantity=2,
        side="BUY",
        price=100.0,
        metadata={"exchange": "NYSE"},
    )

    assert engine.execute_order(context) is True

    broker.place_order.assert_called_once()
    broker.cancel_order.assert_called_once_with("ORD-BROKER-1", "IBM", 2)
