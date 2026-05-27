from __future__ import annotations


def test_build_smart_money_signal_config_reads_nested_yaml_values() -> None:
    """smart_money.signal YAML 값을 SignalConfig로 변환한다."""
    from src.analysis.smart_money.config import build_smart_money_signal_config

    config = build_smart_money_signal_config(
        {
            "signal": {
                "buy_threshold": 0.62,
                "sell_threshold": -0.42,
                "min_confidence": 0.70,
                "min_confirming_timeframes": 3,
                "weights": {
                    "daily": 0.50,
                    "hourly": 0.30,
                    "minute_5": 0.20,
                },
                "stale_pattern_penalty_per_bar": 0.02,
            }
        }
    )

    assert config.buy_threshold == 0.62
    assert config.sell_threshold == -0.42
    assert config.min_confidence == 0.70
    assert config.min_confirming_timeframes == 3
    assert config.timeframe_weights == {"daily": 0.50, "hourly": 0.30, "minute_5": 0.20}
    assert config.stale_pattern_penalty_per_bar == 0.02


def test_build_smart_money_pattern_config_reads_nested_yaml_values() -> None:
    """smart_money.patterns YAML 값을 SmartMoneyPatternConfig로 변환한다."""
    from src.analysis.smart_money.config import build_smart_money_pattern_config

    config = build_smart_money_pattern_config(
        {
            "patterns": {
                "swing_left": 3,
                "swing_right": 1,
                "fvg_min_gap_pct": 0.004,
                "order_block_lookback": 7,
                "liquidity_sweep_tolerance_pct": 0.002,
                "displacement_atr_multiplier": 1.2,
                "atr_period": 10,
            }
        }
    )

    assert config.swing_left == 3
    assert config.swing_right == 1
    assert config.fvg_min_gap_pct == 0.004
    assert config.order_block_lookback == 7
    assert config.liquidity_sweep_tolerance_pct == 0.002
    assert config.displacement_atr_multiplier == 1.2
    assert config.atr_period == 10


def test_invalid_smart_money_config_values_fall_back_to_defaults() -> None:
    """잘못된 YAML 값은 분석 중단 대신 기본값으로 대체한다."""
    from src.analysis.smart_money.config import (
        build_smart_money_pattern_config,
        build_smart_money_signal_config,
    )
    from src.analysis.smart_money.models import SignalConfig, SmartMoneyPatternConfig

    signal = build_smart_money_signal_config(
        {
            "signal": {
                "buy_threshold": "not-a-number",
                "weights": {"daily": "bad", "hourly": 0.3, "minute_5": 0.2},
            }
        }
    )
    patterns = build_smart_money_pattern_config(
        {
            "patterns": {
                "swing_left": 0,
                "fvg_min_gap_pct": -1,
                "order_block_lookback": "bad",
            }
        }
    )

    assert signal.buy_threshold == SignalConfig().buy_threshold
    assert signal.timeframe_weights == SignalConfig().timeframe_weights
    assert patterns == SmartMoneyPatternConfig()
