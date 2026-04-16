import logging
from typing import List

from src.broker.base import BaseBroker
from src.data.api_client import KISAPIClient
from src.data.models import Account, Order, StockPrice


class KISBroker(BaseBroker):
    """KIS-backed broker adapter."""

    def __init__(self, is_mock: bool = True, market: str = "KR", **kwargs):
        self.client = KISAPIClient(is_mock=is_mock, market=market, **kwargs)
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        try:
            self.client._ensure_token()
            return True
        except Exception as exc:
            self.logger.error(f"KIS connect failed: {exc}")
            return False

    def get_current_price(self, symbol: str) -> float:
        return self.client.get_current_price(symbol)

    def place_order(self, order: Order, exchange: str = "NASD") -> str:
        return self.client.place_order(order, exchange=exchange)

    def cancel_order(self, order_id: str, symbol: str, quantity: int) -> dict:
        return self.client.cancel_order(order_id, symbol, quantity)

    def get_account_balance(self) -> Account:
        return self.client.get_account_balance()

    def get_minute_price(self, symbol: str, interval: int = 1, count: int = 100) -> List[StockPrice]:
        return self.client.get_minute_price(symbol, interval, count)

    def get_daily_price(self, symbol: str, count: int = 100) -> List[StockPrice]:
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
        prices = self.client.get_daily_price_history(symbol, start_date, end_date)
        return prices[-count:] if len(prices) > count else prices
