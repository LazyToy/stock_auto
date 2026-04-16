import logging
from typing import List

from src.broker.base import BaseBroker
from src.data.models import Account, Order, StockPrice


class ShinhanBroker(BaseBroker):
    """Placeholder broker implementation."""

    def __init__(self, **kwargs):
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        self.logger.error("Shinhan API connect not implemented.")
        return False

    def get_current_price(self, symbol: str) -> float:
        raise NotImplementedError("Shinhan API not available.")

    def place_order(self, order: Order, exchange: str = "NASD") -> str:
        raise NotImplementedError("Shinhan API not available.")

    def cancel_order(self, order_id: str, symbol: str, quantity: int) -> dict:
        raise NotImplementedError("Shinhan API not available.")

    def get_account_balance(self) -> Account:
        raise NotImplementedError("Shinhan API not available.")

    def get_minute_price(self, symbol: str, interval: int = 1, count: int = 100) -> List[StockPrice]:
        raise NotImplementedError("Shinhan API not available.")

    def get_daily_price(self, symbol: str, count: int = 100) -> List[StockPrice]:
        raise NotImplementedError("Shinhan API not available.")
