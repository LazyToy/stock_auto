"""Order manager with a small saga-style rollback flow."""

import logging
from datetime import datetime

from src.data.api_client import KISAPIClient
from src.data.models import Order, OrderSide
from src.utils.database import DatabaseManager, TradeRecord

logger = logging.getLogger(__name__)


class OrderSaga:
    """Execute an order with minimal compensation support."""

    def __init__(self, api_client: KISAPIClient, db_manager: DatabaseManager, broker=None):
        self.api = api_client
        self.db = db_manager
        self.broker = broker
        self.transactions: list[str] = []

    def execute(self, order: Order, exchange: str | None = None) -> bool:
        """Run the order flow and compensate on failure."""
        try:
            if order.side == OrderSide.BUY and not self._check_balance(order):
                logger.warning(f"Insufficient balance for order: {order}")
                return False

            if not self._place_order(order, exchange=exchange):
                self._compensate("PLACE_ORDER_FAILED", order)
                return False

            if not self._record_transaction(order, exchange=exchange):
                logger.error("Failed to record transaction to DB")

            logger.info(f"Order saga completed successfully: {order.order_id}")
            return True
        except Exception as exc:
            logger.error(f"Saga execution failed: {exc}")
            self._compensate("UNEXPECTED_ERROR", order)
            return False

    def _check_balance(self, order: Order) -> bool:
        """Check whether available cash is enough for a buy order."""
        try:
            balance = self.api.get_balance()
            unit_price = order.price or 0
            if unit_price <= 0:
                current_price_fn = getattr(self.api, "get_current_price", None)
                if callable(current_price_fn):
                    unit_price = current_price_fn(order.symbol) or 0

            if unit_price <= 0:
                logger.warning("Unable to resolve price for balance check: %s", order.symbol)
                return False

            required_amount = unit_price * order.quantity * 1.00015
            if balance["deposit"] >= required_amount:
                logger.info(
                    f"Balance check passed: required={required_amount}, available={balance['deposit']}"
                )
                return True
            return False
        except Exception as exc:
            logger.error(f"Balance check error: {exc}")
            return False

    def _place_order(self, order: Order, exchange: str | None = None) -> bool:
        """Submit an order and persist the returned order id."""
        try:
            if self.broker is not None:
                order_id = self.broker.place_order(
                    order,
                    exchange=self._resolve_exchange(exchange),
                )
            else:
                order_id = self.api.place_order(
                    order,
                    exchange=self._resolve_exchange(exchange),
                )
            if order_id:
                order.order_id = str(order_id)
                self.transactions.append("ORDER_PLACED")
                return True
            logger.error(f"Order placement failed without an order id: {order}")
            return False
        except Exception as exc:
            logger.error(f"Order placement error: {exc}")
            return False

    def _record_transaction(self, order: Order, exchange: str | None = None) -> bool:
        """Record the executed order when a DB manager is available."""
        try:
            if not self.db:
                return False

            if hasattr(self.db, "add_trade"):
                self.db.add_trade(order)
                self.transactions.append("DB_RECORDED")
                return True

            if hasattr(self.db, "insert_trade"):
                trade = TradeRecord(
                    timestamp=(order.created_at or datetime.now()).isoformat(),
                    symbol=order.symbol,
                    side=order.side.name,
                    quantity=order.quantity,
                    price=order.price or 0,
                    amount=(order.price or 0) * order.quantity,
                    reason="ORDER_SAGA",
                    market=self._resolve_market(exchange),
                )
                self.db.insert_trade(trade)
                self.transactions.append("DB_RECORDED")
                return True

            logger.warning("DB manager does not expose add_trade or insert_trade")
            return False
        except Exception as exc:
            logger.error(f"DB record error: {exc}")
            return False

    def _compensate(self, reason: str, order: Order):
        """Run compensation steps in reverse order."""
        logger.warning(f"Starting compensation for {reason}")

        for step in reversed(self.transactions):
            if step == "ORDER_PLACED" and order.order_id:
                logger.info(f"Compensating by canceling order {order.order_id}")
                try:
                    if self.broker is not None:
                        self.broker.cancel_order(order.order_id, order.symbol, order.quantity)
                    else:
                        self.api.cancel_order(order.order_id, order.symbol, order.quantity)
                except Exception as exc:
                    logger.error(f"Failed to cancel order during compensation: {exc}")

            elif step == "DB_RECORDED":
                logger.info(f"Compensating DB record for order {order.order_id}")
                try:
                    if self.db and hasattr(self.db, "_get_connection"):
                        with self.db._get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE trades SET reason = ? WHERE id = "
                                "(SELECT id FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT 1)",
                                (f"CANCELLED (compensation: {reason})", order.symbol),
                            )
                except Exception as exc:
                    logger.error(f"DB compensation failed: {exc}")

        logger.warning("Compensation completed")

    def _resolve_exchange(self, exchange: str | None = None) -> str:
        """Resolve a broker exchange code from the active API market."""
        if exchange:
            return exchange
        market = getattr(self.api, "market", "KR")
        if market == "US":
            return "NASD"
        return "KR"

    def _resolve_market(self, exchange: str | None = None) -> str:
        """Resolve a market/audit code for persistence."""
        if exchange:
            return exchange
        return getattr(self.api, "market", "KR")
