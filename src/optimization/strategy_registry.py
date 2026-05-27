"""AutoML strategy metadata and dashboard label normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class StrategySpec:
    """Parameter metadata used by the genetic optimizer and dashboard."""

    strategy_type: str
    display_name: str
    parameter_labels: list[str]
    low_bounds: list[int]
    up_bounds: list[int]

    def validate_param_count(self, params: Sequence[object]) -> bool:
        return len(params) == len(self.parameter_labels)


_STRATEGY_SPECS: dict[str, StrategySpec] = {
    "MACD_RSI": StrategySpec(
        strategy_type="MACD_RSI",
        display_name="MACD+RSI",
        parameter_labels=[
            "Fast EMA",
            "Slow EMA",
            "Signal",
            "RSI Window",
            "RSI Lower",
            "RSI Upper",
        ],
        low_bounds=[5, 21, 5, 10, 20, 60],
        up_bounds=[20, 60, 15, 30, 40, 80],
    ),
    "MA_CROSSOVER": StrategySpec(
        strategy_type="MA_CROSSOVER",
        display_name="MA Crossover",
        parameter_labels=["Short Window", "Long Window"],
        low_bounds=[3, 10],
        up_bounds=[30, 120],
    ),
    "RSI": StrategySpec(
        strategy_type="RSI",
        display_name="RSI",
        parameter_labels=["RSI Window", "RSI Lower", "RSI Upper"],
        low_bounds=[5, 10, 55],
        up_bounds=[40, 45, 90],
    ),
    "MACD": StrategySpec(
        strategy_type="MACD",
        display_name="MACD",
        parameter_labels=["Fast EMA", "Slow EMA", "Signal"],
        low_bounds=[5, 21, 5],
        up_bounds=[20, 60, 15],
    ),
    "BOLLINGER": StrategySpec(
        strategy_type="BOLLINGER",
        display_name="Bollinger Bands",
        parameter_labels=["Period", "Std Dev x10", "Band Proximity bps"],
        low_bounds=[10, 10, 0],
        up_bounds=[40, 35, 500],
    ),
    "ENSEMBLE_VOTE": StrategySpec(
        strategy_type="ENSEMBLE_VOTE",
        display_name="Ensemble Vote",
        parameter_labels=["Trend Vote Threshold", "Mean Reversion Vote Threshold"],
        low_bounds=[1, 1],
        up_bounds=[2, 2],
    ),
    "RESILIENT_RECLAIM": StrategySpec(
        strategy_type="RESILIENT_RECLAIM",
        display_name="Resilient Reclaim",
        parameter_labels=[
            "High Window",
            "Momentum Window",
            "Reclaim Lookback",
            "High Proximity bps",
            "Min Residual Momentum bps",
            "Failure Buffer bps",
        ],
        low_bounds=[126, 20, 5, 9300, 0, 9200],
        up_bounds=[252, 126, 60, 10100, 1500, 9900],
    ),
}

_ALIASES = {
    "MACD+RSI": "MACD_RSI",
    "MACD_RSI": "MACD_RSI",
    "MACD RSI": "MACD_RSI",
    "MA": "MA_CROSSOVER",
    "MA CROSSOVER": "MA_CROSSOVER",
    "MA_CROSSOVER": "MA_CROSSOVER",
    "MOVING AVERAGE": "MA_CROSSOVER",
    "RSI": "RSI",
    "MACD": "MACD",
    "BB": "BOLLINGER",
    "BOLLINGER": "BOLLINGER",
    "BOLLINGER BANDS": "BOLLINGER",
    "ENSEMBLE": "ENSEMBLE_VOTE",
    "ENSEMBLE VOTE": "ENSEMBLE_VOTE",
    "ENSEMBLE_VOTE": "ENSEMBLE_VOTE",
    "VOTE": "ENSEMBLE_VOTE",
    "RESILIENT": "RESILIENT_RECLAIM",
    "RESILIENT RECLAIM": "RESILIENT_RECLAIM",
    "RESILIENT_RECLAIM": "RESILIENT_RECLAIM",
    "RECLAIM": "RESILIENT_RECLAIM",
}


def normalize_strategy_type(strategy_type: str | None) -> str:
    """Normalize dashboard labels, CLI aliases, and internal IDs."""
    key = (strategy_type or "MACD_RSI").strip().upper().replace("-", " ")
    key = " ".join(key.split())
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _STRATEGY_SPECS:
        return key
    raise ValueError(f"지원하지 않는 AutoML 전략입니다: {strategy_type}")


def get_strategy_spec(strategy_type: str | None = None) -> StrategySpec:
    """Return metadata for a supported AutoML strategy."""
    return _STRATEGY_SPECS[normalize_strategy_type(strategy_type)]


def strategy_options() -> dict[str, str]:
    """Dashboard-friendly option labels mapped to internal strategy IDs."""
    return {
        spec.display_name: spec.strategy_type
        for spec in _STRATEGY_SPECS.values()
    }


def supported_strategy_types() -> list[str]:
    """Return stable internal strategy IDs."""
    return list(_STRATEGY_SPECS)
