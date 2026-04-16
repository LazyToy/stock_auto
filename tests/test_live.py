"""Tests for the live trading engine and risk manager."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.data.models import Account, Order, OrderSide, OrderType
from src.live.engine import LiveTradingEngine
from src.live.risk_manager import RiskManager


class TestRiskManager:
    def test_risk_check_position_limit(self):
        manager = RiskManager(max_position_size=1_000_000)

        order = Order(
            symbol="005930",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=10,
            price=50_000,
            created_at=None,
        )
        assert manager.check_order(order, current_positions_value=0) is True

        order.quantity = 21
        assert manager.check_order(order, current_positions_value=0) is False

    def test_daily_loss_limit(self):
        manager = RiskManager(max_daily_loss=50_000)

        assert manager.check_daily_loss(current_daily_loss=40_000) is True
        assert manager.check_daily_loss(current_daily_loss=60_000) is False


class TestLiveTradingEngine:
    @patch("src.data.api_client.KISAPIClient")
    def test_engine_initialization(self, mock_client_cls):
        strategy = Mock()

        engine = LiveTradingEngine(
            strategy=strategy,
            symbols=["005930"],
            api_client=mock_client_cls,
        )

        assert engine.strategy == strategy
        assert "005930" in engine.symbols

    def test_engine_dry_run_skips_buy_order_submission(self):
        strategy = Mock()
        api_client = Mock()
        api_client.get_current_price.return_value = 50_000
        api_client.get_account_balance.return_value = Account(
            account_number="12345678",
            cash=1_000_000,
            positions=[],
        )

        engine = LiveTradingEngine(
            strategy=strategy,
            symbols=["005930"],
            api_client=api_client,
            dry_run=True,
        )

        engine._place_buy_order("005930")

        api_client.place_order.assert_not_called()

    def test_engine_live_buy_submits_order_object(self):
        strategy = Mock()
        api_client = Mock()
        api_client.get_current_price.return_value = 50_000
        api_client.get_account_balance.return_value = Account(
            account_number="12345678",
            cash=1_000_000,
            positions=[],
        )

        engine = LiveTradingEngine(
            strategy=strategy,
            symbols=["005930"],
            api_client=api_client,
            dry_run=False,
            market="KR",
        )

        engine._place_buy_order("005930")

        api_client.place_order.assert_called_once()
        call_args, call_kwargs = api_client.place_order.call_args
        assert isinstance(call_args[0], Order)
        assert call_args[0].symbol == "005930"
        assert call_args[0].side == OrderSide.BUY
        assert call_args[0].order_type == OrderType.MARKET
        assert call_args[0].price == 0
        assert call_kwargs["exchange"] == "KR"

    def test_engine_us_buy_submits_price_and_default_exchange(self):
        strategy = Mock()
        api_client = Mock()
        api_client.get_current_price.return_value = 111.0
        api_client.get_account_balance.return_value = Account(
            account_number="12345678",
            cash=1_000_000,
            positions=[],
        )

        engine = LiveTradingEngine(
            strategy=strategy,
            symbols=["IBM"],
            api_client=api_client,
            dry_run=False,
            market="US",
        )

        engine._place_buy_order("IBM")

        api_client.place_order.assert_called_once()
        call_args, call_kwargs = api_client.place_order.call_args
        assert isinstance(call_args[0], Order)
        assert call_args[0].symbol == "IBM"
        assert call_args[0].side == OrderSide.BUY
        assert call_args[0].order_type == OrderType.MARKET
        assert call_args[0].price == 111.0
        assert call_kwargs["exchange"] == "NASD"

    def test_engine_live_buy_prefers_broker_when_present(self):
        strategy = Mock()
        api_client = Mock()
        api_client.get_current_price.return_value = 50_000
        api_client.get_account_balance.return_value = Account(
            account_number="12345678",
            cash=1_000_000,
            positions=[],
        )
        broker = Mock()

        engine = LiveTradingEngine(
            strategy=strategy,
            symbols=["005930"],
            api_client=api_client,
            broker=broker,
            dry_run=False,
            market="KR",
        )

        engine._place_buy_order("005930")

        broker.place_order.assert_called_once()
        api_client.place_order.assert_not_called()

    def test_process_symbol_buy_flow_prefers_broker_submission(self):
        strategy = Mock()
        strategy.generate_signals.return_value = pd.DataFrame({"signal": [1]})
        api_client = Mock()
        api_client.get_current_price.return_value = 50_000
        api_client.get_account_balance.return_value = Account(
            account_number="12345678",
            cash=1_000_000,
            positions=[],
        )
        broker = Mock()

        engine = LiveTradingEngine(
            strategy=strategy,
            symbols=["005930"],
            api_client=api_client,
            broker=broker,
            dry_run=False,
            market="KR",
        )
        engine._fetch_price_data = Mock(
            return_value=pd.DataFrame({"close": [50_000], "volume": [1_000]})
        )

        engine._process_symbol("005930")

        broker.place_order.assert_called_once()
        api_client.place_order.assert_not_called()
        strategy.generate_signals.assert_called_once()
        assert engine._state["last_signals"]["005930"]["signal"] == 1
