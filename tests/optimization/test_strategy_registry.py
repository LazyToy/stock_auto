import pytest

from src.optimization.strategy_registry import (
    get_strategy_spec,
    normalize_strategy_type,
    strategy_options,
    supported_strategy_types,
)


def test_strategy_registry_maps_dashboard_labels_to_real_strategy_ids():
    assert normalize_strategy_type("MA Crossover") == "MA_CROSSOVER"
    assert normalize_strategy_type("RSI") == "RSI"
    assert normalize_strategy_type("MACD") == "MACD"
    assert normalize_strategy_type("Bollinger Bands") == "BOLLINGER"
    assert normalize_strategy_type("Ensemble Vote") == "ENSEMBLE_VOTE"
    assert normalize_strategy_type("Resilient Reclaim") == "RESILIENT_RECLAIM"
    assert normalize_strategy_type("MACD_RSI") == "MACD_RSI"


def test_strategy_spec_exposes_parameter_space_and_labels_for_optimizer():
    spec = get_strategy_spec("Bollinger Bands")

    assert spec.strategy_type == "BOLLINGER"
    assert spec.parameter_labels == ["Period", "Std Dev x10", "Band Proximity bps"]
    assert spec.low_bounds == [10, 10, 0]
    assert spec.up_bounds == [40, 35, 500]


def test_strategy_options_are_dashboard_friendly():
    options = strategy_options()

    assert "MACD+RSI" in options
    assert options["MACD+RSI"] == "MACD_RSI"
    assert options["MA Crossover"] == "MA_CROSSOVER"
    assert options["Ensemble Vote"] == "ENSEMBLE_VOTE"
    assert options["Resilient Reclaim"] == "RESILIENT_RECLAIM"


def test_ensemble_vote_spec_keeps_parameter_space_small():
    spec = get_strategy_spec("Ensemble Vote")

    assert spec.strategy_type == "ENSEMBLE_VOTE"
    assert spec.parameter_labels == ["Trend Vote Threshold", "Mean Reversion Vote Threshold"]
    assert spec.low_bounds == [1, 1]
    assert spec.up_bounds == [2, 2]


def test_resilient_reclaim_spec_exposes_research_parameter_space():
    spec = get_strategy_spec("Resilient Reclaim")

    assert spec.strategy_type == "RESILIENT_RECLAIM"
    assert spec.parameter_labels == [
        "High Window",
        "Momentum Window",
        "Reclaim Lookback",
        "High Proximity bps",
        "Min Residual Momentum bps",
        "Failure Buffer bps",
    ]
    assert spec.low_bounds == [126, 20, 5, 9300, 0, 9200]
    assert spec.up_bounds == [252, 126, 60, 10100, 1500, 9900]
    assert "RESILIENT_RECLAIM" in supported_strategy_types()


def test_unknown_strategy_type_fails_fast():
    with pytest.raises(ValueError):
        get_strategy_spec("Not A Strategy")
