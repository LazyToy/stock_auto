from abc import ABC, abstractmethod
from typing import List

from src.data.models import Account, Order, StockPrice


class BaseBroker(ABC):
    """Abstract broker interface."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect and authenticate the broker session."""
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Return the latest price for a symbol."""
        pass

    @abstractmethod
    def place_order(self, order: Order, exchange: str = "NASD") -> str:
        """Submit an order and return the broker order id."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str, quantity: int) -> dict:
        """Cancel an order."""
        pass

    @abstractmethod
    def get_account_balance(self) -> Account:
        """Return account balance and positions."""
        pass

    @abstractmethod
    def get_minute_price(self, symbol: str, interval: int = 1, count: int = 100) -> List[StockPrice]:
        """Return minute-bar price history."""
        pass

    @abstractmethod
    def get_daily_price(self, symbol: str, count: int = 100) -> List[StockPrice]:
        """Return daily price history."""
        pass
