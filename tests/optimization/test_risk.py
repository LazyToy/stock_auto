import pandas as pd

from src.optimization.risk import RiskConfig, simulate_long_only_with_risk


def test_max_holding_days_exits_position_without_sell_signal():
    frame = pd.DataFrame(
        {
            "High": [100, 102, 103, 104, 105],
            "Low": [99, 100, 101, 102, 103],
            "Close": [100, 101, 102, 103, 104],
        }
    )
    events = pd.Series([1, 0, 0, 0, 0], index=frame.index)

    result = simulate_long_only_with_risk(
        frame,
        events,
        RiskConfig(max_holding_days=2),
        fee=0.0,
        slippage=0.0,
        tax=0.0,
    )

    assert result.trade_count == 2
    assert result.exit_reasons == {"max_holding": 1}
    assert result.position[-1] == 0


def test_atr_stop_exits_and_cooldown_blocks_immediate_reentry():
    frame = pd.DataFrame(
        {
            "High": [100, 102, 103, 100, 101, 102],
            "Low": [99, 100, 101, 90, 99, 100],
            "Close": [100, 101, 102, 95, 100, 101],
        }
    )
    events = pd.Series([1, 0, 0, 1, 1, 0], index=frame.index)

    result = simulate_long_only_with_risk(
        frame,
        events,
        RiskConfig(atr_stop_multiplier=1.0, cooldown_days=2),
        fee=0.0,
        slippage=0.0,
        tax=0.0,
    )

    assert result.exit_reasons == {"atr_stop": 1}
    assert result.position[4] == 0


def test_trailing_stop_exits_after_peak_reversal():
    frame = pd.DataFrame(
        {
            "High": [100, 105, 112, 111, 110],
            "Low": [99, 103, 110, 104, 103],
            "Close": [100, 104, 111, 105, 104],
        }
    )
    events = pd.Series([1, 0, 0, 0, 0], index=frame.index)

    result = simulate_long_only_with_risk(
        frame,
        events,
        RiskConfig(trailing_stop_pct=0.05),
        fee=0.0,
        slippage=0.0,
        tax=0.0,
    )

    assert result.exit_reasons == {"trailing_stop": 1}
    assert result.position[-1] == 0


def test_risk_exit_reason_takes_precedence_when_signal_and_stop_overlap():
    frame = pd.DataFrame(
        {
            "High": [100, 102, 103, 100],
            "Low": [99, 100, 101, 90],
            "Close": [100, 101, 102, 95],
        }
    )
    events = pd.Series([1, 0, -1, 0], index=frame.index)

    result = simulate_long_only_with_risk(
        frame,
        events,
        RiskConfig(atr_stop_multiplier=1.0),
        fee=0.0,
        slippage=0.0,
        tax=0.0,
    )

    assert result.exit_reasons == {"atr_stop": 1}
