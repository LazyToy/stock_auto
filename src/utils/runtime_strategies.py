"""Shared strategy builders for runtime scripts."""

from src.strategies.bollinger import BollingerBandStrategy
from src.strategies.macd import MACDStrategy
from src.strategies.moving_average import DualMAStrategy
from src.strategies.multi_indicator import MultiIndicatorStrategy
from src.strategies.rsi import RSIStrategy

INDICATOR_STRATEGY_CHOICES = ["ma", "rsi", "bb", "macd", "multi"]


def build_indicator_strategy(strategy_name: str):
    """Build a named indicator strategy used by runtime scripts."""
    if strategy_name == "ma":
        return DualMAStrategy()
    if strategy_name == "rsi":
        return RSIStrategy()
    if strategy_name == "bb":
        return BollingerBandStrategy()
    if strategy_name == "macd":
        return MACDStrategy()
    if strategy_name == "multi":
        return MultiIndicatorStrategy()
    raise ValueError(f"Unsupported strategy: {strategy_name}")
