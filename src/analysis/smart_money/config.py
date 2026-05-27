"""Smart Money YAML 설정 변환 유틸리티."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from src.analysis.smart_money.models import SignalConfig, SmartMoneyPatternConfig


def build_smart_money_signal_config(values: Mapping[str, Any] | None) -> SignalConfig:
    """smart_money YAML dict를 SignalConfig로 변환한다."""
    defaults = SignalConfig()
    section = _mapping_section(values, "signal")
    weights = _coerce_weights(
        section.get("weights", section.get("timeframe_weights", defaults.timeframe_weights)),
        defaults.timeframe_weights,
    )

    return SignalConfig(
        buy_threshold=_coerce_float(section.get("buy_threshold"), defaults.buy_threshold),
        sell_threshold=_coerce_float(section.get("sell_threshold"), defaults.sell_threshold),
        min_confidence=_coerce_float(
            section.get("min_confidence"),
            defaults.min_confidence,
            min_value=0.0,
            max_value=1.0,
        ),
        min_confirming_timeframes=_coerce_int(
            section.get("min_confirming_timeframes"),
            defaults.min_confirming_timeframes,
            min_value=1,
        ),
        timeframe_weights=weights,
        stale_pattern_penalty_per_bar=_coerce_float(
            section.get("stale_pattern_penalty_per_bar"),
            defaults.stale_pattern_penalty_per_bar,
            min_value=0.0,
        ),
        max_patterns_per_type=_coerce_int(
            section.get("max_patterns_per_type"),
            defaults.max_patterns_per_type,
            min_value=1,
        ),
        conflict_penalty=_coerce_float(
            section.get("conflict_penalty"),
            defaults.conflict_penalty,
            min_value=0.0,
            max_value=1.0,
        ),
        insufficient_data_penalty=_coerce_float(
            section.get("insufficient_data_penalty"),
            defaults.insufficient_data_penalty,
            min_value=0.0,
            max_value=1.0,
        ),
        invalidation_proximity_penalty=_coerce_float(
            section.get("invalidation_proximity_penalty"),
            defaults.invalidation_proximity_penalty,
            min_value=0.0,
            max_value=1.0,
        ),
    )


def build_smart_money_pattern_config(values: Mapping[str, Any] | None) -> SmartMoneyPatternConfig:
    """smart_money YAML dict를 SmartMoneyPatternConfig로 변환한다."""
    defaults = SmartMoneyPatternConfig()
    section = _mapping_section(values, "patterns")
    return SmartMoneyPatternConfig(
        swing_left=_coerce_int(section.get("swing_left"), defaults.swing_left, min_value=1),
        swing_right=_coerce_int(section.get("swing_right"), defaults.swing_right, min_value=1),
        fvg_min_gap_pct=_coerce_float(
            section.get("fvg_min_gap_pct"),
            defaults.fvg_min_gap_pct,
            min_value=0.0,
        ),
        order_block_lookback=_coerce_int(
            section.get("order_block_lookback"),
            defaults.order_block_lookback,
            min_value=1,
        ),
        liquidity_sweep_tolerance_pct=_coerce_float(
            section.get("liquidity_sweep_tolerance_pct"),
            defaults.liquidity_sweep_tolerance_pct,
            min_value=0.0,
        ),
        displacement_atr_multiplier=_coerce_float(
            section.get("displacement_atr_multiplier"),
            defaults.displacement_atr_multiplier,
            min_value=0.0,
        ),
        atr_period=_coerce_int(section.get("atr_period"), defaults.atr_period, min_value=1),
    )


def load_smart_money_analysis_config() -> tuple[SignalConfig, SmartMoneyPatternConfig]:
    """config/trading.yaml의 smart_money.signal/patterns 설정을 로드한다."""
    from src.utils.config_loader import get_trading_config

    trading_config = get_trading_config()
    smart_money_config = trading_config.get("smart_money", {})
    if not isinstance(smart_money_config, Mapping):
        return SignalConfig(), SmartMoneyPatternConfig()
    return (
        build_smart_money_signal_config(smart_money_config),
        build_smart_money_pattern_config(smart_money_config),
    )


def _mapping_section(values: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    section = values.get(key, {})
    return section if isinstance(section, Mapping) else {}


def _coerce_float(
    value: Any,
    default: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


def _coerce_int(value: Any, default: int, *, min_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def _coerce_weights(value: Any, default: dict[str, float]) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return dict(default)
    weights: dict[str, float] = {}
    for key in ("daily", "hourly", "minute_5"):
        parsed = _coerce_float(value.get(key), float("nan"), min_value=0.0)
        if math.isnan(parsed):
            return dict(default)
        weights[key] = parsed
    return weights
