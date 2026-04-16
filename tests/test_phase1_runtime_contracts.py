import argparse
import importlib
import importlib.util
import logging
import logging.handlers
import sys
import builtins
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.data.api_client import KISAPIClient
from src.data.models import Account, Order, OrderSide, OrderType, Position
from src.live.engine import LiveTradingEngine
from src.trader.self_healing import OrderContext, RecoveryAction, SelfHealingEngine


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


def _load_module_from_path(module_path: Path):
    module_name = f"phase1_{module_path.stem}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _deny_file_handler(monkeypatch):
    monkeypatch.setattr(
        logging,
        "FileHandler",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("file denied")),
    )


def _prime_script_import_dependencies(monkeypatch):
    _import_auto_trader_with_dummy_handlers(monkeypatch)


def test_setup_logging_survives_file_handler_permission_error(monkeypatch):
    logger_module = importlib.import_module("src.utils.logger")
    importlib.reload(logger_module)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    monkeypatch.setattr(
        logging.handlers,
        "TimedRotatingFileHandler",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("timed denied")),
    )
    monkeypatch.setattr(
        logging.handlers,
        "RotatingFileHandler",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("rotating denied")),
    )

    logger = logger_module.setup_logging(name="phase1_logger_test", log_dir="logs")

    assert logger.name == "phase1_logger_test"


def test_get_balance_includes_position_exchange(monkeypatch):
    client = KISAPIClient(
        app_key="test_key",
        app_secret="test_secret",
        account_number="12345678",
        is_mock=True,
        market="US",
    )
    monkeypatch.setattr(
        client,
        "get_account_balance",
        lambda exchange="NASD": Account(
            account_number="12345678",
            cash=1000.0,
            positions=[
                Position(
                    symbol="IBM",
                    quantity=2,
                    avg_price=100.0,
                    current_price=110.0,
                    exchange="NYSE",
                )
            ],
        ),
    )

    balance = client.get_balance()

    assert balance["stocks"][0]["exchange"] == "NYSE"


def test_sell_stock_uses_order_object_for_real_order(monkeypatch, tmp_path):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", tmp_path)

    mock_api = MagicMock()
    trader = AutoTrader(api_client=mock_api, universe=["005930"], dry_run=False, market="KR")

    trader._sell_stock("005930", 3)

    mock_api.place_order.assert_called_once()
    call_args, call_kwargs = mock_api.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_args[0].symbol == "005930"
    assert call_args[0].side == OrderSide.SELL
    assert call_args[0].order_type == OrderType.MARKET
    assert call_args[0].quantity == 3
    assert call_args[0].price == 0
    assert call_kwargs["exchange"] == "KR"


def test_sell_stock_us_uses_current_price_and_exchange(monkeypatch, tmp_path):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", tmp_path)

    mock_api = MagicMock()
    mock_api.get_current_price.return_value = 111.0
    trader = AutoTrader(api_client=mock_api, universe=["IBM"], dry_run=False, market="US")

    trader._sell_stock("IBM", 3, "NYSE")

    mock_api.place_order.assert_called_once()
    call_args, call_kwargs = mock_api.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_args[0].symbol == "IBM"
    assert call_args[0].side == OrderSide.SELL
    assert call_args[0].order_type == OrderType.MARKET
    assert call_args[0].quantity == 3
    assert call_args[0].price == 111.0
    assert call_kwargs["exchange"] == "NYSE"


def test_auto_trader_place_order_prefers_broker_when_present(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())

    mock_api = MagicMock()
    broker = MagicMock()
    trader = AutoTrader(
        api_client=mock_api,
        broker=broker,
        universe=["005930"],
        dry_run=False,
        market="KR",
    )
    trader.notifier = None
    trader.audit_logger = None
    trader.db = None

    trader._place_order("005930", 2, OrderSide.BUY, 50_000.0, exchange="KR")

    broker.place_order.assert_called_once()
    mock_api.place_order.assert_not_called()


def test_auto_trader_init_skips_regime_model_load_when_detector_has_no_loader(monkeypatch, tmp_path):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", tmp_path)
    (tmp_path / "regime_model.pkl").write_bytes(b"placeholder")

    trader = AutoTrader(api_client=MagicMock(), universe=["005930"], dry_run=True, market="KR")

    assert trader.regime_detector is not None


def test_check_market_sentiment_passes_exchange_to_us_sell_order(monkeypatch, tmp_path):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", tmp_path)

    mock_api = MagicMock()
    mock_api.get_current_price.return_value = 111.0
    mock_api.get_balance.return_value = {
        "stocks": [
            {
                "symbol": "IBM",
                "quantity": 9,
                "exchange": "NYSE",
            }
        ]
    }

    trader = AutoTrader(api_client=mock_api, universe=["IBM"], dry_run=False, market="US")
    trader.sentiment_analyzer.analyze_ticker = MagicMock(return_value=-0.8)

    trader.check_market_sentiment()

    mock_api.place_order.assert_called_once()
    call_args, call_kwargs = mock_api.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_args[0].symbol == "IBM"
    assert call_args[0].side == OrderSide.SELL
    assert call_args[0].order_type == OrderType.MARKET
    assert call_args[0].quantity == 4
    assert call_args[0].price == 111.0
    assert call_kwargs["exchange"] == "NYSE"


def test_rebalance_defaults_to_kr_exchange_for_kr_buy_orders(monkeypatch, tmp_path):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())

    mock_api = MagicMock()
    trader = AutoTrader(api_client=mock_api, universe=["005930"], dry_run=False, market="KR")
    trader.notifier = None
    trader.audit_logger = None
    trader.db = None

    account = Account(account_number="12345678", cash=1_000_000.0, positions=[])
    top_stocks = [
        {
            "ticker": "005930",
            "score": 2.0,
            "current_price": 50_000.0,
        }
    ]

    trader._rebalance_portfolio(account, top_stocks, sold_tickers=[])

    mock_api.place_order.assert_called_once()
    call_args, call_kwargs = mock_api.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_args[0].symbol == "005930"
    assert call_args[0].side == OrderSide.BUY
    assert call_args[0].order_type == OrderType.MARKET
    assert call_args[0].price == 0
    assert call_kwargs["exchange"] == "KR"


def test_auto_trader_place_order_prefers_broker_when_present(monkeypatch):
    auto_trader_module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    AutoTrader = auto_trader_module.AutoTrader
    monkeypatch.setattr(auto_trader_module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(auto_trader_module, "send_notification", MagicMock())

    mock_api = MagicMock()
    broker = MagicMock()
    trader = AutoTrader(
        api_client=mock_api,
        universe=["IBM"],
        dry_run=False,
        market="US",
        broker=broker,
    )
    trader.notifier = None
    trader.audit_logger = None
    trader.db = None

    trader._place_order("IBM", 3, OrderSide.BUY, 111.0, exchange="NYSE")

    broker.place_order.assert_called_once()
    mock_api.place_order.assert_not_called()


def test_self_healing_cancel_calls_api_client_with_order_id_symbol_quantity():
    mock_api = MagicMock()
    engine = SelfHealingEngine(api_client=mock_api)

    action = RecoveryAction(
        action_type="CANCEL_ALL",
        symbol="005930",
        quantity=7,
        order_id="ORD-123",
    )

    engine._execute_recovery_action(action)

    mock_api.cancel_order.assert_called_once_with("ORD-123", "005930", 7)


def test_self_healing_submit_order_passes_exchange_metadata_to_api_client():
    mock_api = MagicMock()
    mock_api.place_order.return_value = "ORD-API-1"
    engine = SelfHealingEngine(api_client=mock_api)

    context = engine.state_machine.context
    assert context is None

    from src.trader.self_healing import OrderContext

    order_context = OrderContext(
        symbol="IBM",
        quantity=3,
        side="BUY",
        price=100.0,
        metadata={"exchange": "NYSE"},
    )

    order_id = engine._submit_order(order_context)

    assert order_id == "ORD-API-1"
    mock_api.place_order.assert_called_once()
    call_args, call_kwargs = mock_api.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_kwargs["exchange"] == "NYSE"


def test_order_saga_execute_accepts_string_order_id_from_api_client(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.get_balance.return_value = {"deposit": 1_000_000}
    mock_api.place_order.return_value = "ORD-1"
    mock_db = MagicMock()
    saga = module.OrderSaga(api_client=mock_api, db_manager=mock_db)

    order = Order(
        symbol="005930",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=1,
        price=50_000,
        created_at=datetime.now(),
    )

    assert saga.execute(order) is True
    assert order.order_id == "ORD-1"
    mock_api.place_order.assert_called_once_with(order, exchange="KR")
    mock_db.add_trade.assert_called_once_with(order)


def test_order_saga_compensation_uses_cancel_order_contract(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    saga = module.OrderSaga(api_client=mock_api, db_manager=None)
    saga.transactions = ["ORDER_PLACED"]

    order = Order(
        symbol="005930",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=2,
        price=50_000,
        created_at=datetime.now(),
        order_id="ORD-CANCEL-1",
    )

    saga._compensate("TEST", order)

    mock_api.cancel_order.assert_called_once_with("ORD-CANCEL-1", "005930", 2)


def test_order_saga_balance_check_uses_current_price_for_market_buy(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.get_balance.return_value = {"deposit": 100_000}
    mock_api.get_current_price.return_value = 50_000
    mock_db = MagicMock()
    saga = module.OrderSaga(api_client=mock_api, db_manager=mock_db)

    order = Order(
        symbol="005930",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=3,
        price=0,
        created_at=datetime.now(),
    )

    assert saga.execute(order) is False
    mock_api.place_order.assert_not_called()
    mock_api.get_current_price.assert_called_once_with("005930")


def test_order_saga_record_transaction_uses_api_market_when_available(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.market = "US"
    mock_api.get_balance.return_value = {"deposit": 1_000_000}
    mock_api.place_order.return_value = "ORD-DB-1"
    captured = {}

    class DummyDb:
        def insert_trade(self, trade):
            captured["trade"] = trade

    saga = module.OrderSaga(api_client=mock_api, db_manager=DummyDb())
    order = Order(
        symbol="IBM",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=1,
        price=100.0,
        created_at=datetime.now(),
    )

    assert saga.execute(order) is True
    assert captured["trade"].market == "US"


def test_order_saga_execute_prefers_broker_when_present(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.market = "US"
    mock_api.get_balance.return_value = {"deposit": 1_000_000}
    broker = MagicMock()
    broker.place_order.return_value = "ORD-BROKER-EXEC-1"
    mock_db = MagicMock()
    saga = module.OrderSaga(api_client=mock_api, db_manager=mock_db, broker=broker)

    order = Order(
        symbol="IBM",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=1,
        price=100.0,
        created_at=datetime.now(),
    )

    assert saga.execute(order) is True
    broker.place_order.assert_called_once_with(order, exchange="NASD")
    mock_api.place_order.assert_not_called()
    assert order.order_id == "ORD-BROKER-EXEC-1"


def test_order_saga_execute_passes_explicit_exchange_to_broker(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.market = "US"
    mock_api.get_balance.return_value = {"deposit": 1_000_000}
    broker = MagicMock()
    broker.place_order.return_value = "ORD-BROKER-EXCHANGE-1"
    saga = module.OrderSaga(api_client=mock_api, db_manager=None, broker=broker)

    order = Order(
        symbol="IBM",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=1,
        price=100.0,
        created_at=datetime.now(),
    )

    assert saga.execute(order, exchange="NYSE") is True
    broker.place_order.assert_called_once_with(order, exchange="NYSE")
    mock_api.place_order.assert_not_called()
    assert order.order_id == "ORD-BROKER-EXCHANGE-1"


def test_order_saga_execute_passes_explicit_exchange_to_api_fallback(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.market = "US"
    mock_api.get_balance.return_value = {"deposit": 1_000_000}
    mock_api.place_order.return_value = "ORD-API-EXCHANGE-1"
    saga = module.OrderSaga(api_client=mock_api, db_manager=None)

    order = Order(
        symbol="IBM",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=1,
        price=100.0,
        created_at=datetime.now(),
    )

    assert saga.execute(order, exchange="NYSE") is True
    mock_api.place_order.assert_called_once_with(order, exchange="NYSE")


def test_order_saga_compensation_prefers_broker_cancel_when_present(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    broker = MagicMock()
    saga = module.OrderSaga(api_client=mock_api, db_manager=None, broker=broker)
    saga.transactions = ["ORDER_PLACED"]

    order = Order(
        symbol="IBM",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=2,
        price=100.0,
        created_at=datetime.now(),
        order_id="ORD-BROKER-CANCEL-1",
    )

    saga._compensate("TEST", order)

    broker.cancel_order.assert_called_once_with("ORD-BROKER-CANCEL-1", "IBM", 2)
    mock_api.cancel_order.assert_not_called()


def test_order_saga_record_transaction_prefers_explicit_exchange_market(monkeypatch):
    sys.modules.pop("src.trader.order_manager", None)
    module = importlib.import_module("src.trader.order_manager")

    mock_api = MagicMock()
    mock_api.market = "US"
    mock_api.get_balance.return_value = {"deposit": 1_000_000}
    mock_api.place_order.return_value = "ORD-DB-EXCHANGE-1"
    captured = {}

    class DummyDb:
        def insert_trade(self, trade):
            captured["trade"] = trade

    saga = module.OrderSaga(api_client=mock_api, db_manager=DummyDb())
    order = Order(
        symbol="IBM",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=1,
        price=100.0,
        created_at=datetime.now(),
    )

    assert saga.execute(order, exchange="NYSE") is True
    assert captured["trade"].market == "NYSE"


def test_self_healing_submit_order_passes_exchange_metadata_to_broker():
    broker = MagicMock()
    broker.place_order.return_value = "ORD-BROKER-1"
    engine = SelfHealingEngine(api_client=None, broker=broker)

    order_context = OrderContext(
        symbol="IBM",
        quantity=3,
        side="BUY",
        price=100.0,
        metadata={"exchange": "NYSE"},
    )

    order_id = engine._submit_order(order_context)

    assert order_id == "ORD-BROKER-1"
    broker.place_order.assert_called_once()
    call_args, call_kwargs = broker.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_kwargs["exchange"] == "NYSE"


def test_live_engine_us_sell_uses_position_exchange_and_price():
    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1000.0,
        positions=[
            Position(
                symbol="IBM",
                quantity=3,
                avg_price=100.0,
                current_price=111.0,
                exchange="NYSE",
            )
        ],
    )

    engine = LiveTradingEngine(
        strategy=MagicMock(),
        symbols=["IBM"],
        api_client=mock_api,
        dry_run=False,
        market="US",
        enable_telegram=False,
    )
    engine.circuit_breaker = None

    engine._place_sell_order("IBM")

    mock_api.place_order.assert_called_once()
    call_args, call_kwargs = mock_api.place_order.call_args
    assert isinstance(call_args[0], Order)
    assert call_args[0].symbol == "IBM"
    assert call_args[0].side == OrderSide.SELL
    assert call_args[0].order_type == OrderType.MARKET
    assert call_args[0].quantity == 3
    assert call_args[0].price == 111.0
    assert call_kwargs["exchange"] == "NYSE"


def test_run_scheduler_import_survives_file_handler_permission_error(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    _deny_file_handler(monkeypatch)

    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_scheduler.py"
    )

    assert callable(module.main)


def test_run_us_trading_import_survives_file_handler_permission_error(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    _deny_file_handler(monkeypatch)

    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_us_trading.py"
    )

    assert callable(module.job)


def test_run_us_growth_import_survives_file_handler_permission_error(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    _deny_file_handler(monkeypatch)

    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_us_growth.py"
    )

    assert callable(module.job)


def test_run_single_strategy_passes_market_to_api_client(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    mock_api = MagicMock()
    mock_trader = MagicMock()
    auto_trader_cls = MagicMock(return_value=mock_trader)
    api_client_cls = MagicMock(return_value=mock_api)

    monkeypatch.setattr(module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module, "KISAPIClient", api_client_cls)
    monkeypatch.setattr(module, "AutoTrader", auto_trader_cls)

    module.run_single_strategy(market="KR", strategy_type="momentum", dry_run=True)

    api_client_cls.assert_called_once_with(market="KR", is_mock=True)


def test_run_single_strategy_uses_shared_runtime_broker_helper(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    mock_api = MagicMock()
    mock_broker = MagicMock()
    auto_trader_cls = MagicMock(return_value=MagicMock())
    build_client = MagicMock(return_value=mock_api)
    build_broker = MagicMock(return_value=mock_broker)

    monkeypatch.setattr(module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "build_kis_broker", build_broker, raising=False)
    monkeypatch.setattr(module, "AutoTrader", auto_trader_cls)

    module.run_single_strategy(market="KR", strategy_type="momentum", dry_run=True)

    build_broker.assert_called_once_with(
        market="KR",
        is_mock=True,
        broker_cls=module.KISBroker,
    )
    assert auto_trader_cls.call_args.kwargs["broker"] is mock_broker


def test_run_enhanced_strategy_passes_market_to_api_client(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    mock_api = MagicMock()
    mock_trader = MagicMock()
    auto_trader_cls = MagicMock(return_value=mock_trader)
    api_client_cls = MagicMock(return_value=mock_api)

    monkeypatch.setattr(module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(module, "ML_AVAILABLE", True)
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module, "KISAPIClient", api_client_cls)
    monkeypatch.setattr(module, "AutoTrader", auto_trader_cls)
    monkeypatch.setattr(module.StrategyFactory, "create", MagicMock(return_value=MagicMock()))

    module.run_enhanced_strategy(market="KR", base_strategy="momentum", ai_filter="ml_rf", dry_run=True)

    api_client_cls.assert_called_once_with(market="KR", is_mock=True)


def test_run_multi_portfolio_creates_and_reuses_api_clients_per_market(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    class FakePortfolioConfig:
        def __init__(self, name, strategy_name, allocation_pct, market="KR", max_stocks=5):
            self.name = name
            self.strategy_name = strategy_name
            self.allocation_pct = allocation_pct
            self.market = market
            self.max_stocks = max_stocks

    class FakeManager:
        def __init__(self, total_capital):
            self.total_capital = total_capital
            self.portfolios = {}

        def add_portfolio(self, config):
            self.portfolios[config.name] = {"config": config}

        def generate_report(self):
            return "ok"

    clients_by_market = {
        "KR": MagicMock(name="kr_client"),
        "US": MagicMock(name="us_client"),
    }

    def make_client(*, market, is_mock):
        assert is_mock is True
        return clients_by_market[market]

    auto_trader_cls = MagicMock()

    monkeypatch.setattr(module, "PORTFOLIO_AVAILABLE", True)
    monkeypatch.setattr(module, "TRADING_AVAILABLE", True)
    monkeypatch.setattr(module, "MultiPortfolioManager", FakeManager)
    monkeypatch.setattr(module, "PortfolioConfig", FakePortfolioConfig)
    monkeypatch.setattr(
        module.Config,
        "load_universe",
        lambda: {"KR": ["005930"], "US": ["AAPL"]},
    )
    monkeypatch.setattr(module, "KISAPIClient", MagicMock(side_effect=make_client))
    monkeypatch.setattr(module, "AutoTrader", auto_trader_cls)
    monkeypatch.setattr(builtins, "print", MagicMock())

    module.run_multi_portfolio(
        portfolios=[
            {"name": "KR_1", "strategy": "momentum", "market": "KR", "allocation": 40},
            {"name": "KR_2", "strategy": "value", "market": "KR", "allocation": 30},
            {"name": "US_1", "strategy": "value", "market": "US", "allocation": 30},
        ],
        dry_run=True,
    )

    assert module.KISAPIClient.call_args_list == [
        (( ), {"market": "KR", "is_mock": True}),
        (( ), {"market": "US", "is_mock": True}),
    ]
    assert auto_trader_cls.call_args_list[0].kwargs["api_client"] is clients_by_market["KR"]
    assert auto_trader_cls.call_args_list[1].kwargs["api_client"] is clients_by_market["KR"]
    assert auto_trader_cls.call_args_list[2].kwargs["api_client"] is clients_by_market["US"]


def test_describe_execution_mode_distinguishes_dry_run_and_mock_orders():
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    dry_run_message = module.describe_execution_mode(is_mock=True, dry_run=True)
    mock_order_message = module.describe_execution_mode(is_mock=True, dry_run=False)

    assert "broker=mock" in dry_run_message
    assert "orders=dry-run" in dry_run_message
    assert "broker=mock" in mock_order_message
    assert "orders=mock" in mock_order_message


def test_execution_mode_helper_resolves_legacy_mode_aliases():
    module = importlib.import_module("src.utils.execution_mode")

    is_mock, dry_run = module.resolve_execution_flags(
        argparse.Namespace(
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode="real",
        ),
        legacy_mode_attr="mode",
        legacy_mode_map={
            "mock": (True, False),
            "real": (False, False),
        },
    )

    assert is_mock is False
    assert dry_run is False


def test_execution_mode_helper_blocks_unconfirmed_order_submission():
    module = importlib.import_module("src.utils.execution_mode")
    printed = []

    with pytest.raises(SystemExit):
        module.validate_execution_mode_or_exit(
            argparse.Namespace(
                confirm_order_submission=False,
                confirm_real_broker=False,
            ),
            is_mock=True,
            dry_run=False,
            print_fn=lambda message: printed.append(message),
            real_broker_error="ERROR: --real-broker requires --confirm-real-broker",
        )

    assert any("--confirm-order-submission" in line for line in printed)


def test_execution_mode_helper_loads_real_credentials():
    module = importlib.import_module("src.utils.execution_mode")

    app_key, app_secret, account = module.load_kis_credentials(
        is_mock=False,
        getenv=lambda key: f"value-for-{key}",
    )

    assert app_key == "value-for-KIS_REAL_APP_KEY"
    assert app_secret == "value-for-KIS_REAL_APP_SECRET"
    assert account == "value-for-KIS_REAL_ACCOUNT_NUMBER"


def test_runtime_client_helper_builds_market_only_client():
    module = importlib.import_module("src.utils.runtime_clients")
    client_cls = MagicMock(return_value="client")

    client = module.build_kis_client(
        market="KR",
        is_mock=True,
        client_cls=client_cls,
    )

    assert client == "client"
    client_cls.assert_called_once_with(
        market="KR",
        is_mock=True,
    )


def test_runtime_client_helper_builds_explicit_credential_client():
    module = importlib.import_module("src.utils.runtime_clients")
    client_cls = MagicMock(return_value="client")

    client = module.build_kis_client(
        app_key="real-key",
        app_secret="real-secret",
        account_number="12345678",
        is_mock=False,
        client_cls=client_cls,
    )

    assert client == "client"
    client_cls.assert_called_once_with(
        app_key="real-key",
        app_secret="real-secret",
        account_number="12345678",
        is_mock=False,
    )


def test_runtime_client_helper_builds_broker_via_factory():
    module = importlib.import_module("src.utils.runtime_clients")
    factory_cls = MagicMock()
    factory_cls.create_broker.return_value = "broker"

    broker = module.build_kis_broker(
        market="US",
        is_mock=False,
        app_key="real-key",
        app_secret="real-secret",
        account_number="12345678",
        broker_factory_cls=factory_cls,
    )

    assert broker == "broker"
    factory_cls.create_broker.assert_called_once_with(
        "kis",
        market="US",
        is_mock=False,
        app_key="real-key",
        app_secret="real-secret",
        account_number="12345678",
    )


def test_selector_import_survives_missing_yfinance_dependency(monkeypatch):
    sys.modules.pop("src.strategies.selector", None)
    module = importlib.import_module("src.strategies.selector")

    assert module.StockSelector is not None
    assert module.yf is None


def test_stock_selector_download_data_requires_yfinance_when_unavailable():
    module = importlib.import_module("src.strategies.selector")
    selector = module.StockSelector(["005930"])

    if module.yf is not None:
        pytest.skip("yfinance is installed in this environment")

    with pytest.raises(RuntimeError):
        selector.download_data()


def test_execution_mode_helper_adds_shared_cli_flags():
    module = importlib.import_module("src.utils.execution_mode")
    parser = argparse.ArgumentParser()

    module.add_execution_mode_arguments(parser, live_flag_help="custom live help")

    args = parser.parse_args(["--mock-order", "--confirm-order-submission"])

    assert hasattr(args, "dry_run")
    assert hasattr(args, "mock_order")
    assert hasattr(args, "real_broker")
    assert hasattr(args, "live")
    assert hasattr(args, "confirm_order_submission")
    assert hasattr(args, "confirm_real_broker")
    assert args.mock_order is True
    assert args.confirm_order_submission is True


def test_execution_mode_helper_optionally_adds_legacy_mode_alias():
    module = importlib.import_module("src.utils.execution_mode")
    parser = argparse.ArgumentParser()

    module.add_execution_mode_arguments(
        parser,
        include_legacy_mode=True,
        legacy_mode_help="legacy mode help",
    )

    args = parser.parse_args(["--mode", "real"])

    assert args.mode == "real"


def test_execution_mode_helper_emits_execution_banner_lines():
    module = importlib.import_module("src.utils.execution_mode")
    printed = []

    module.emit_execution_banner(
        print_fn=lambda message: printed.append(message),
        title="Runtime",
        details=["mode=single", "market=KR"],
        is_mock=True,
        dry_run=True,
    )

    assert printed[0] == "=" * 60
    assert "Runtime" in printed[1]
    assert any("mode=single" in line for line in printed)
    assert any("주문 dry-run: True" in line for line in printed)
    assert any("broker=mock" in line and "orders=dry-run" in line for line in printed)


def test_runtime_strategy_helper_builds_indicator_strategies():
    module = importlib.import_module("src.utils.runtime_strategies")

    ma = module.build_indicator_strategy("ma")
    rsi = module.build_indicator_strategy("rsi")
    bb = module.build_indicator_strategy("bb")
    macd = module.build_indicator_strategy("macd")
    multi = module.build_indicator_strategy("multi")

    assert ma.__class__.__name__ == "DualMAStrategy"
    assert rsi.__class__.__name__ == "RSIStrategy"
    assert bb.__class__.__name__ == "BollingerBandStrategy"
    assert macd.__class__.__name__ == "MACDStrategy"
    assert multi.__class__.__name__ == "MultiIndicatorStrategy"


def test_run_backtest_uses_shared_indicator_strategy_helper(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    fake_strategy = MagicMock()
    fake_strategy.name = "SharedStrategy"
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbol="005930",
            strategy="ma",
            start="20250101",
            end="20251231",
            capital=1_000_000,
        ),
    )
    monkeypatch.setattr(module, "build_indicator_strategy", MagicMock(return_value=fake_strategy))
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module.os, "getenv", lambda key: None)
    client = MagicMock()
    client.get_daily_price_history.return_value = []
    monkeypatch.setattr(module, "KISAPIClient", MagicMock(return_value=client))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    module.main()

    module.build_indicator_strategy.assert_called_once_with("ma")


def test_run_backtest_main_configures_logging(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbol="005930",
            strategy="ma",
            start="20250101",
            end="20251231",
            capital=1_000_000,
        ),
    )
    monkeypatch.setattr(module, "setup_logging", MagicMock())
    fake_strategy = MagicMock()
    fake_strategy.name = "SharedStrategy"
    monkeypatch.setattr(module, "build_indicator_strategy", MagicMock(return_value=fake_strategy))
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module.os, "getenv", lambda key: None)
    client = MagicMock()
    client.get_daily_price_history.return_value = []
    monkeypatch.setattr(module, "KISAPIClient", MagicMock(return_value=client))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    module.main()

    module.setup_logging.assert_called_once_with()


def test_run_backtest_uses_shared_runtime_client_helper(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    )

    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbol="005930",
            strategy="ma",
            start="20250101",
            end="20251231",
            capital=1_000_000,
        ),
    )
    fake_strategy = MagicMock()
    fake_strategy.name = "SharedStrategy"
    monkeypatch.setattr(module, "build_indicator_strategy", MagicMock(return_value=fake_strategy))
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module.os, "getenv", lambda key: None)
    client = MagicMock()
    client.get_daily_price_history.return_value = []
    build_client = MagicMock(return_value=client)
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    module.main()

    build_client.assert_called_once_with(
        app_key=None,
        app_secret=None,
        account_number=None,
        is_mock=True,
        client_cls=module.KISAPIClient,
    )


def test_runtime_logging_helper_handles_file_handler_permission_error(monkeypatch):
    module = importlib.import_module("src.utils.runtime_logging")

    basic_config = MagicMock()
    warning_logger = MagicMock()
    monkeypatch.setattr(
        module.logging,
        "FileHandler",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("file denied")),
    )
    monkeypatch.setattr(module.logging, "basicConfig", basic_config)
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: warning_logger)

    configured = module.configure_script_logging(
        file_name="test.log",
        fmt="%(message)s",
        configured=False,
    )

    assert configured is True
    basic_config.assert_called_once()
    warning_logger.warning.assert_called_once()


def test_runtime_logging_helper_skips_reconfiguration_when_already_configured(monkeypatch):
    module = importlib.import_module("src.utils.runtime_logging")
    basic_config = MagicMock()
    monkeypatch.setattr(module.logging, "basicConfig", basic_config)

    configured = module.configure_script_logging(
        file_name="test.log",
        fmt="%(message)s",
        configured=True,
    )

    assert configured is True
    basic_config.assert_not_called()


def test_resolve_execution_flags_defaults_to_mock_dry_run():
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    is_mock, dry_run = module.resolve_execution_flags(
        module.argparse.Namespace(
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
        )
    )

    assert is_mock is True
    assert dry_run is True


def test_resolve_execution_flags_live_alias_maps_to_mock_order():
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    is_mock, dry_run = module.resolve_execution_flags(
        module.argparse.Namespace(
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=True,
        )
    )

    assert is_mock is True
    assert dry_run is False


def test_resolve_execution_flags_real_broker_maps_to_real_submit():
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    is_mock, dry_run = module.resolve_execution_flags(
        module.argparse.Namespace(
            dry_run=False,
            mock_order=False,
            real_broker=True,
            live=False,
        )
    )

    assert is_mock is False
    assert dry_run is False


def test_run_auto_trading_prints_execution_mode(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "experiments" / "run_auto_trading.py"
    )

    printed = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(map(str, args))))
    monkeypatch.setattr(module.Config, "KIS_APP_KEY", "key")
    monkeypatch.setattr(module.Config, "KIS_APP_SECRET", "secret")
    monkeypatch.setattr(module.Config, "KIS_ACCOUNT_NUMBER", "acct")
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    trader = MagicMock()
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=trader))

    module.kr_trading_job()

    assert any("broker=mock" in line and "orders=dry-run" in line for line in printed)


def test_run_auto_trading_uses_shared_runtime_client_helper(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "experiments" / "run_auto_trading.py"
    )

    build_client = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.Config, "KIS_APP_KEY", "key")
    monkeypatch.setattr(module.Config, "KIS_APP_SECRET", "secret")
    monkeypatch.setattr(module.Config, "KIS_ACCOUNT_NUMBER", "acct")
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=MagicMock()))

    module.kr_trading_job()

    build_client.assert_called_once_with(
        app_key="key",
        app_secret="secret",
        account_number="acct",
        is_mock=True,
        market="KR",
        client_cls=module.KISAPIClient,
    )


def test_run_us_trading_logs_execution_mode(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "experiments" / "run_us_trading.py"
    )

    info_messages = []
    monkeypatch.setattr(module, "configure_logging", lambda: None)
    monkeypatch.setattr(module.logger, "info", lambda message: info_messages.append(message))
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"US": ["AAPL"]})
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    trader = MagicMock()
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=trader))
    monkeypatch.setattr(module, "load_dotenv", lambda: None)

    module.job()

    assert any("broker=mock" in line and "orders=dry-run" in line for line in info_messages)


def test_run_us_trading_uses_shared_runtime_client_helper(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "experiments" / "run_us_trading.py"
    )

    build_client = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(module, "configure_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"US": ["AAPL"]})
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=MagicMock()))

    module.job()

    build_client.assert_called_once_with(
        app_key=module.Config.KIS_APP_KEY,
        app_secret=module.Config.KIS_APP_SECRET,
        account_number=module.Config.KIS_ACCOUNT_NUMBER,
        is_mock=True,
        market="US",
        client_cls=module.KISAPIClient,
    )


def test_run_us_growth_logs_execution_mode(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "experiments" / "run_us_growth.py"
    )

    info_messages = []
    monkeypatch.setattr(module, "configure_logging", lambda: None)
    monkeypatch.setattr(module.logger, "info", lambda message: info_messages.append(message))
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    trader = MagicMock()
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=trader))
    monkeypatch.setattr(module, "load_dotenv", lambda: None)

    module.job()

    assert any("broker=mock" in line and "orders=dry-run" in line for line in info_messages)


def test_run_us_growth_uses_shared_runtime_client_helper(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "experiments" / "run_us_growth.py"
    )

    build_client = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(module, "configure_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=MagicMock()))

    module.job()

    build_client.assert_called_once_with(
        app_key=module.Config.KIS_APP_KEY,
        app_secret=module.Config.KIS_APP_SECRET,
        account_number=module.Config.KIS_ACCOUNT_NUMBER,
        is_mock=True,
        market="US",
        client_cls=module.KISAPIClient,
    )


def test_run_scheduler_monitoring_logs_execution_mode(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_scheduler.py"
    )

    info_messages = []
    monkeypatch.setattr(module.logger, "info", lambda message: info_messages.append(message))
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    trader = MagicMock()
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=trader))

    module.run_monitoring("KR")

    assert any("broker=mock" in line and "orders=dry-run" in line for line in info_messages)


def test_run_scheduler_monitoring_uses_shared_runtime_client_helper(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_scheduler.py"
    )

    build_client = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(module.logger, "info", lambda message: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=MagicMock()))

    module.run_monitoring("US")

    build_client.assert_called_once_with(
        app_key=module.Config.KIS_APP_KEY,
        app_secret=module.Config.KIS_APP_SECRET,
        account_number=module.Config.KIS_ACCOUNT_NUMBER,
        is_mock=True,
        market="US",
        client_cls=module.KISAPIClient,
    )


def test_init_dashboard_data_uses_shared_runtime_client_helper(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "init_dashboard_data.py"
    )

    client_kr = MagicMock(name="kr_client")
    client_us = MagicMock(name="us_client")
    build_client = MagicMock(side_effect=[client_kr, client_us])
    trader_kr = MagicMock()
    trader_us = MagicMock()

    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module, "AutoTrader", MagicMock(side_effect=[trader_kr, trader_us]))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    module.main()

    assert build_client.call_args_list == [
        (( ), {
            "app_key": module.Config.KIS_APP_KEY,
            "app_secret": module.Config.KIS_APP_SECRET,
            "account_number": module.Config.KIS_ACCOUNT_NUMBER,
            "is_mock": True,
            "market": "KR",
            "client_cls": module.KISAPIClient,
        }),
        (( ), {
            "app_key": module.Config.KIS_APP_KEY,
            "app_secret": module.Config.KIS_APP_SECRET,
            "account_number": module.Config.KIS_ACCOUNT_NUMBER,
            "is_mock": True,
            "market": "US",
            "client_cls": module.KISAPIClient,
        }),
    ]
    trader_kr.export_dashboard_state.assert_called_once_with()
    trader_us.export_dashboard_state.assert_called_once_with()


def test_run_trading_main_prints_explicit_order_mode_wording(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

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
            dry_run=False,
            mock_order=False,
            real_broker=False,
            confirm_order_submission=False,
            confirm_real_broker=False,
            live=False,
        ),
    )
    monkeypatch.setattr(module, "run_single_strategy", MagicMock())

    module.main()

    assert any("주문 dry-run: True" in line for line in printed)
    assert not any("모의투자:" in line for line in printed)
    assert module.LIVE_FLAG_HELP == "주문 제출 실행 (기본값: broker=mock, orders=dry-run)"


def test_run_trading_main_uses_shared_execution_banner(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    banner = MagicMock()
    monkeypatch.setattr(module, "emit_execution_banner", banner, raising=False)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            mode="single",
            market="KR",
            strategy="momentum",
            ai_filter="ml_rf",
            capital=1_000_000,
            dry_run=False,
            mock_order=False,
            real_broker=False,
            confirm_order_submission=False,
            confirm_real_broker=False,
            live=False,
        ),
    )
    monkeypatch.setattr(module, "run_single_strategy", MagicMock())

    module.main()

    banner.assert_called_once()
    assert banner.call_args.kwargs["is_mock"] is True
    assert banner.call_args.kwargs["dry_run"] is True


def test_run_trading_main_passes_real_broker_flags_to_single_strategy(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            mode="single",
            market="KR",
            strategy="momentum",
            ai_filter="ml_rf",
            capital=1_000_000,
            dry_run=False,
            mock_order=False,
            real_broker=True,
            confirm_order_submission=True,
            confirm_real_broker=True,
            live=False,
        ),
    )
    run_single = MagicMock()
    monkeypatch.setattr(module, "run_single_strategy", run_single)

    module.main()

    run_single.assert_called_once_with(
        market="KR",
        strategy_type="momentum",
        dry_run=False,
        capital=1_000_000,
        is_mock=False,
    )


def test_run_trading_main_dispatches_compare_mode(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            mode="compare",
            market="US",
            strategy="momentum",
            ai_filter="ml_rf",
            capital=3_000_000,
            dry_run=False,
            mock_order=True,
            real_broker=False,
            confirm_order_submission=True,
            confirm_real_broker=False,
            live=False,
        ),
    )
    run_compare = MagicMock()
    monkeypatch.setattr(module, "run_ml_strategy_comparison", run_compare, raising=False)

    module.main()

    run_compare.assert_called_once_with(
        market="US",
        dry_run=False,
        capital=3_000_000,
        is_mock=True,
    )


def test_run_trading_main_blocks_real_broker_without_confirmation(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

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
            dry_run=False,
            mock_order=False,
            real_broker=True,
            confirm_order_submission=True,
            confirm_real_broker=False,
            live=False,
        ),
    )
    run_single = MagicMock()
    monkeypatch.setattr(module, "run_single_strategy", run_single)

    with pytest.raises(SystemExit):
        module.main()

    run_single.assert_not_called()
    assert any("--confirm-real-broker" in line for line in printed)


def test_run_trading_main_blocks_mock_order_without_submission_confirmation(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

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
            dry_run=False,
            mock_order=True,
            real_broker=False,
            confirm_order_submission=False,
            confirm_real_broker=False,
            live=False,
        ),
    )
    run_single = MagicMock()
    monkeypatch.setattr(module, "run_single_strategy", run_single)

    with pytest.raises(SystemExit):
        module.main()

    run_single.assert_not_called()
    assert any("--confirm-order-submission" in line for line in printed)


def test_run_trading_main_passes_mock_order_with_submission_confirmation(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            mode="single",
            market="KR",
            strategy="momentum",
            ai_filter="ml_rf",
            capital=1_000_000,
            dry_run=False,
            mock_order=True,
            real_broker=False,
            confirm_order_submission=True,
            confirm_real_broker=False,
            live=False,
        ),
    )
    run_single = MagicMock()
    monkeypatch.setattr(module, "run_single_strategy", run_single)

    module.main()

    run_single.assert_called_once_with(
        market="KR",
        strategy_type="momentum",
        dry_run=False,
        capital=1_000_000,
        is_mock=True,
    )


def test_run_scheduler_main_passes_explicit_mock_to_scheduled_run_single_strategy(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_scheduler.py"
    )

    class _FakeDateTime:
        @staticmethod
        def now():
            return datetime(2026, 3, 30, 9, 30)

    calls = []

    monkeypatch.setattr(module, "configure_logging", lambda: None)
    monkeypatch.setattr(module, "KISWebSocketClient", MagicMock(return_value=MagicMock(start=MagicMock())))
    monkeypatch.setattr(module, "datetime", _FakeDateTime)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module,
        "run_single_strategy",
        lambda **kwargs: calls.append(kwargs),
    )

    sleep_calls = {"count": 0}

    def _stop_after_one_loop(_seconds):
        sleep_calls["count"] += 1
        raise SystemExit(0)

    monkeypatch.setattr(module.time, "sleep", _stop_after_one_loop)

    with pytest.raises(SystemExit):
        module.main()

    assert calls == [
        {
            "market": "KR",
            "strategy_type": "momentum",
            "dry_run": True,
            "is_mock": True,
        }
    ]


def test_readiness_audit_update_documents_real_broker_confirmation():
    content = (
        Path(__file__).resolve().parents[1]
        / "REAL_READINESS_AUDIT_UPDATE_2026-03-27.md"
    ).read_text(encoding="utf-8")

    assert "--dry-run" in content
    assert "--mock-order" in content
    assert "--confirm-order-submission" in content
    assert "--real-broker" in content
    assert "--confirm-real-broker" in content
    assert "future work" not in content.lower()


def test_trainer_uses_shared_runtime_client_helper(monkeypatch):
    module = importlib.import_module("src.train.trainer")

    client = MagicMock()
    client.get_daily_price_history.return_value = [
        SimpleNamespace(date="20250102", open=1, high=1, low=1, close=1, volume=1),
    ]
    build_client = MagicMock(return_value=client)
    strategy = MagicMock()

    class _FakeDateTime:
        @staticmethod
        def now():
            return datetime(2026, 3, 27)

    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module, "datetime", _FakeDateTime)
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module.StrategyFactory, "create", MagicMock(return_value=strategy))
    monkeypatch.setattr(module, "send_notification", lambda message: None)
    monkeypatch.setattr(module.os, "makedirs", lambda *args, **kwargs: None)

    module.train_monthly_model(market="KR", strategy_type="ml_rf")

    build_client.assert_called_once_with(
        market="KR",
        is_mock=True,
        client_cls=module.KISAPIClient,
    )
    strategy.train.assert_called_once()
    strategy.save_model.assert_called_once()


def test_run_single_strategy_loads_latest_saved_ml_model(monkeypatch):
    _prime_script_import_dependencies(monkeypatch)
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1] / "scripts" / "run_trading.py"
    )

    strategy = MagicMock()
    strategy.name = "LoadedStrategy"
    monkeypatch.setattr(module.Config, "load_universe", lambda: {"KR": ["005930"]})
    monkeypatch.setattr(module, "build_kis_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(module, "build_kis_broker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(module, "AutoTrader", MagicMock(return_value=MagicMock(run_rebalancing=MagicMock())))
    monkeypatch.setattr(module.StrategyFactory, "create", MagicMock(return_value=strategy))
    monkeypatch.setattr(
        module,
        "_find_latest_runtime_model_path",
        MagicMock(return_value=Path("models/kr_ml_rf_202603.pkl")),
        raising=False,
    )

    module.run_single_strategy(
        market="KR",
        strategy_type="ml_rf",
        dry_run=True,
        is_mock=True,
    )

    strategy.load_model.assert_called_once_with("models\\kr_ml_rf_202603.pkl")


def test_readiness_audit_update_documents_run_live_real_broker_guard():
    content = (
        Path(__file__).resolve().parents[1]
        / "REAL_READINESS_AUDIT_UPDATE_2026-03-27.md"
    ).read_text(encoding="utf-8")

    assert "run_live.py" in content
    assert "--real-broker --confirm-order-submission --confirm-real-broker" in content
    assert "--mode mock|real" in content


def test_run_live_resolve_execution_flags_defaults_to_mock_dry_run():
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    is_mock, dry_run = module.resolve_execution_flags(
        module.argparse.Namespace(
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode=None,
        )
    )

    assert is_mock is True
    assert dry_run is True


def test_run_live_main_blocks_real_broker_without_confirmation(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    printed = []
    monkeypatch.setattr(
        builtins,
        "print",
        lambda *args, **kwargs: printed.append(" ".join(map(str, args))),
    )
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930",
            strategy="ma",
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode="real",
            confirm_order_submission=True,
            confirm_real_broker=False,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    client_cls = MagicMock()
    engine_cls = MagicMock()
    monkeypatch.setattr(module, "KISAPIClient", client_cls)
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)

    with pytest.raises(SystemExit):
        module.main()

    client_cls.assert_not_called()
    engine_cls.assert_not_called()
    assert any("--confirm-real-broker" in line for line in printed)


def test_run_live_main_defaults_to_mock_dry_run(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930,000660",
            strategy="ma",
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode=None,
            confirm_order_submission=False,
            confirm_real_broker=False,
        ),
    )
    logger = MagicMock()
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: logger)
    client_cls = MagicMock()
    engine = MagicMock()
    engine_cls = MagicMock(return_value=engine)
    monkeypatch.setattr(module, "KISAPIClient", client_cls)
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")

    module.main()

    client_cls.assert_called_once_with(
        app_key="value-for-KIS_APP_KEY",
        app_secret="value-for-KIS_APP_SECRET",
        account_number="value-for-KIS_ACCOUNT_NUMBER",
        is_mock=True,
    )
    assert engine_cls.call_args.kwargs["dry_run"] is True


def test_run_live_main_blocks_mock_order_without_submission_confirmation(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    printed = []
    monkeypatch.setattr(
        builtins,
        "print",
        lambda *args, **kwargs: printed.append(" ".join(map(str, args))),
    )
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930",
            strategy="ma",
            dry_run=False,
            mock_order=True,
            real_broker=False,
            live=False,
            mode=None,
            confirm_order_submission=False,
            confirm_real_broker=False,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    client_cls = MagicMock()
    engine_cls = MagicMock()
    monkeypatch.setattr(module, "KISAPIClient", client_cls)
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)

    with pytest.raises(SystemExit):
        module.main()

    client_cls.assert_not_called()
    engine_cls.assert_not_called()
    assert any("--confirm-order-submission" in line for line in printed)


def test_run_live_main_passes_mock_order_with_submission_confirmation(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930,000660",
            strategy="ma",
            dry_run=False,
            mock_order=True,
            real_broker=False,
            live=False,
            mode=None,
            confirm_order_submission=True,
            confirm_real_broker=False,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    logger = MagicMock()
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: logger)
    client_cls = MagicMock()
    engine = MagicMock()
    engine_cls = MagicMock(return_value=engine)
    monkeypatch.setattr(module, "KISAPIClient", client_cls)
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)

    module.main()

    client_cls.assert_called_once_with(
        app_key="value-for-KIS_APP_KEY",
        app_secret="value-for-KIS_APP_SECRET",
        account_number="value-for-KIS_ACCOUNT_NUMBER",
        is_mock=True,
    )
    assert engine_cls.call_args.kwargs["dry_run"] is False


def test_run_live_main_allows_real_broker_with_confirmation(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930,000660",
            strategy="ma",
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode="real",
            confirm_order_submission=True,
            confirm_real_broker=True,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    logger = MagicMock()
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: logger)
    client_cls = MagicMock()
    engine = MagicMock()
    engine_cls = MagicMock(return_value=engine)
    monkeypatch.setattr(module, "KISAPIClient", client_cls)
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)

    module.main()

    client_cls.assert_called_once_with(
        app_key="value-for-KIS_REAL_APP_KEY",
        app_secret="value-for-KIS_REAL_APP_SECRET",
        account_number="value-for-KIS_REAL_ACCOUNT_NUMBER",
        is_mock=False,
    )
    engine_cls.assert_called_once()
    engine.start.assert_called_once_with()


def test_run_live_main_uses_shared_runtime_client_helper(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930",
            strategy="ma",
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode=None,
            confirm_order_submission=False,
            confirm_real_broker=False,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    logger = MagicMock()
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: logger)
    build_client = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    monkeypatch.setattr(module, "LiveTradingEngine", MagicMock(return_value=MagicMock()))

    module.main()

    build_client.assert_called_once_with(
        app_key="value-for-KIS_APP_KEY",
        app_secret="value-for-KIS_APP_SECRET",
        account_number="value-for-KIS_ACCOUNT_NUMBER",
        is_mock=True,
        client_cls=module.KISAPIClient,
    )


def test_run_live_main_uses_shared_runtime_broker_helper(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930",
            strategy="ma",
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode=None,
            confirm_order_submission=False,
            confirm_real_broker=False,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: MagicMock())
    monkeypatch.setattr(module, "build_kis_client", MagicMock(return_value=MagicMock()), raising=False)
    build_broker = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(module, "build_kis_broker", build_broker, raising=False)
    monkeypatch.setattr(module, "KISAPIClient", MagicMock())
    engine_cls = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)

    module.main()

    build_broker.assert_called_once_with(
        app_key="value-for-KIS_APP_KEY",
        app_secret="value-for-KIS_APP_SECRET",
        account_number="value-for-KIS_ACCOUNT_NUMBER",
        is_mock=True,
        client_cls=module.KISAPIClient,
    )
    assert engine_cls.call_args.kwargs["broker"] is build_broker.return_value


def test_run_live_main_uses_shared_runtime_broker_helper(monkeypatch):
    module = _load_module_from_path(
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "experiments"
        / "run_live.py"
    )

    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "setup_logging", lambda: None)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            symbols="005930",
            strategy="ma",
            dry_run=False,
            mock_order=False,
            real_broker=False,
            live=False,
            mode=None,
            confirm_order_submission=False,
            confirm_real_broker=False,
        ),
    )
    monkeypatch.setattr(module.os, "getenv", lambda key: f"value-for-{key}")
    monkeypatch.setattr(module.logging, "getLogger", lambda name=None: MagicMock())
    build_client = MagicMock(return_value=MagicMock())
    build_broker = MagicMock(return_value=MagicMock())
    engine = MagicMock()
    engine_cls = MagicMock(return_value=engine)
    monkeypatch.setattr(module, "build_kis_client", build_client, raising=False)
    monkeypatch.setattr(module, "build_kis_broker", build_broker, raising=False)
    monkeypatch.setattr(module, "LiveTradingEngine", engine_cls)

    module.main()

    build_broker.assert_called_once_with(
        app_key="value-for-KIS_APP_KEY",
        app_secret="value-for-KIS_APP_SECRET",
        account_number="value-for-KIS_ACCOUNT_NUMBER",
        is_mock=True,
        market="KR",
        broker_cls=module.KISBroker,
    )
    assert engine_cls.call_args.kwargs["broker"] is build_broker.return_value
