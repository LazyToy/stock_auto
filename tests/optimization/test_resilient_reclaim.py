import numpy as np
import pandas as pd

from src.optimization.resilient_reclaim import (
    apply_failure_to_fall_filter,
    build_resilient_reclaim_features,
    build_failure_to_fall_filter,
    compare_failure_to_fall_filter,
    compare_atr_stop_variants,
    evaluate_signal_events,
    generate_reclaim_events,
)


def _frame(close):
    close = np.asarray(close, dtype=float)
    return pd.DataFrame(
        {
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 1000,
        },
        index=pd.date_range("2024-01-01", periods=len(close), freq="D"),
    )


def test_resilient_reclaim_features_use_shifted_52w_high_to_avoid_lookahead():
    frame = _frame([100, 105, 103, 110])

    features = build_resilient_reclaim_features(frame, high_window=3)

    assert np.isnan(features["high_52w_previous"].iloc[0])
    assert features["high_52w_previous"].iloc[1] == 101.0
    assert features["high_52w_previous"].iloc[3] == 106.0
    assert round(features["high_52w_proximity"].iloc[3], 4) == round(110 / 106, 4)


def test_resilient_reclaim_features_use_prior_high_not_prior_close():
    frame = _frame([100, 99, 98, 101])
    frame.loc[frame.index[1], "High"] = 120

    features = build_resilient_reclaim_features(frame, high_window=3)

    assert features["high_52w_previous"].iloc[3] == 120.0


def test_resilient_reclaim_features_compute_market_residual_momentum():
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    frame = pd.DataFrame({"Close": [100, 102, 104, 106, 108, 110, 112, 114]}, index=dates)
    benchmark = pd.DataFrame({"Close": [100, 100, 101, 101, 102, 102, 103, 103]}, index=dates)

    features = build_resilient_reclaim_features(
        frame,
        benchmark=benchmark,
        momentum_window=3,
        beta_window=3,
    )

    assert "residual_momentum" in features.columns
    assert features["asset_momentum"].iloc[-1] > features["benchmark_momentum"].iloc[-1]
    assert features["residual_momentum"].iloc[-1] > 0


def test_resilient_reclaim_features_can_remove_sector_momentum_too():
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    frame = pd.DataFrame({"Close": [100, 101, 103, 106, 108, 111, 113, 116]}, index=dates)
    benchmark = pd.DataFrame({"Close": [100, 100, 101, 101, 102, 102, 103, 103]}, index=dates)
    sector = pd.DataFrame({"Close": [100, 101, 102, 104, 105, 107, 108, 110]}, index=dates)

    with_sector = build_resilient_reclaim_features(
        frame,
        benchmark=benchmark,
        sector=sector,
        momentum_window=3,
        beta_window=3,
    )
    without_sector = build_resilient_reclaim_features(
        frame,
        benchmark=benchmark,
        momentum_window=3,
        beta_window=3,
    )

    assert "sector_momentum" in with_sector.columns
    assert with_sector["residual_momentum"].iloc[-1] < without_sector["residual_momentum"].iloc[-1]


def test_resilient_reclaim_features_do_not_double_subtract_correlated_market_and_sector():
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    prices = [100, 101, 102, 103, 104, 105, 106, 107]
    benchmark = pd.DataFrame({"Close": prices}, index=dates)
    sector = pd.DataFrame({"Close": prices}, index=dates)
    frame = pd.DataFrame({"Close": prices}, index=dates)

    features = build_resilient_reclaim_features(
        frame,
        benchmark=benchmark,
        sector=sector,
        momentum_window=3,
        beta_window=3,
    )

    assert "sector_residual_momentum" in features.columns
    assert abs(features["market_residual_momentum"].iloc[-1]) < 1e-9
    assert abs(features["sector_residual_momentum"].iloc[-1]) < 1e-9
    assert abs(features["residual_momentum"].iloc[-1]) < 1e-9


def test_resilient_reclaim_features_do_not_backfill_future_benchmark_values():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    frame = pd.DataFrame({"Close": [100, 101, 102, 103, 104]}, index=dates)
    benchmark = pd.DataFrame({"Close": [200, 201]}, index=dates[-2:])

    features = build_resilient_reclaim_features(
        frame,
        benchmark=benchmark,
        momentum_window=2,
        beta_window=2,
    )

    assert features["benchmark_momentum"].iloc[:3].isna().all()


def test_resilient_reclaim_features_limit_stale_factor_forward_fill():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    frame = pd.DataFrame({"Close": [100, 101, 102, 103, 104, 105]}, index=dates)
    benchmark = pd.DataFrame({"Close": [200, 201]}, index=[dates[0], dates[1]])

    features = build_resilient_reclaim_features(
        frame,
        benchmark=benchmark,
        momentum_window=2,
        beta_window=2,
        max_factor_ffill_days=1,
    )

    assert pd.isna(features["benchmark_close"].iloc[3])
    assert pd.isna(features["benchmark_momentum"].iloc[3])
    assert pd.isna(features["residual_momentum"].iloc[3])


def test_generate_reclaim_events_do_not_buy_when_residual_is_missing():
    frame = _frame([100, 110, 106, 104, 112])
    features = build_resilient_reclaim_features(frame, high_window=4, momentum_window=2)
    features["residual_momentum"] = [0.0, 0.0, -0.01, -0.01, np.nan]

    events = generate_reclaim_events(
        features,
        proximity_threshold=0.98,
        reclaim_lookback=3,
        min_residual_momentum=0.01,
    )

    assert events.iloc[4] == 0


def test_generate_reclaim_events_buy_after_prior_high_reclaim_with_positive_residual():
    frame = _frame([100, 110, 106, 104, 111, 113])
    features = build_resilient_reclaim_features(frame, high_window=4, momentum_window=2)
    features["residual_momentum"] = [0.0, 0.0, -0.01, -0.01, 0.03, 0.04]

    events = generate_reclaim_events(
        features,
        proximity_threshold=0.98,
        reclaim_lookback=3,
        min_residual_momentum=0.01,
    )

    assert events.tolist() == [0, 0, 0, 0, 1, 0]


def test_generate_reclaim_events_sell_when_reclaim_fails():
    frame = _frame([100, 110, 106, 104, 111, 101])
    features = build_resilient_reclaim_features(frame, high_window=4, momentum_window=2)
    features["residual_momentum"] = [0.0, 0.0, -0.01, -0.01, 0.03, -0.02]

    events = generate_reclaim_events(
        features,
        proximity_threshold=0.98,
        reclaim_lookback=3,
        min_residual_momentum=0.01,
        failure_buffer=0.98,
    )

    assert events.iloc[4] == 1
    assert events.iloc[5] == -1


def test_generate_reclaim_events_sell_when_reclaim_fails_after_holding_period():
    frame = _frame([100, 110, 106, 104, 112, 111, 101])
    features = build_resilient_reclaim_features(frame, high_window=4, momentum_window=2)
    features["residual_momentum"] = [0.0, 0.0, -0.01, -0.01, 0.03, 0.02, -0.02]

    events = generate_reclaim_events(
        features,
        proximity_threshold=0.98,
        reclaim_lookback=3,
        min_residual_momentum=0.01,
        failure_buffer=0.98,
    )

    assert events.iloc[4] == 1
    assert events.iloc[5] == 0
    assert events.iloc[6] == -1


def test_generate_reclaim_events_does_not_sell_on_dynamic_high_ratchet():
    frame = _frame([100, 110, 106, 104, 112, 130, 124, 111])
    features = build_resilient_reclaim_features(frame, high_window=4, momentum_window=2)
    features["residual_momentum"] = [0.0, 0.0, -0.01, -0.01, 0.03, 0.04, 0.03, 0.02]

    events = generate_reclaim_events(
        features,
        proximity_threshold=0.98,
        reclaim_lookback=3,
        min_residual_momentum=0.01,
        failure_buffer=0.98,
    )

    assert events.iloc[4] == 1
    assert events.iloc[6] == 0
    assert events.iloc[7] == 0


def test_failure_to_fall_filter_keeps_buy_only_when_factor_falls_and_stock_holds():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    features = pd.DataFrame(
        {
            "close": [100, 101, 102, 101, 102, 90],
            "benchmark_close": [100, 100, 100, 96, 97, 90],
        },
        index=dates,
    )
    events = pd.Series([0, 0, 0, 1, 0, 1], index=dates)

    mask = build_failure_to_fall_filter(
        features,
        lookback=3,
        min_factor_drawdown=0.03,
        max_asset_drawdown=0.03,
    )
    filtered = apply_failure_to_fall_filter(events, mask)

    assert bool(mask.iloc[3]) is True
    assert bool(mask.iloc[5]) is False
    assert filtered.tolist() == [0, 0, 0, 1, 0, 0]


def test_failure_to_fall_filter_blocks_buy_when_factor_is_missing():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    features = pd.DataFrame(
        {
            "close": [100, 101, 102, 103],
            "benchmark_close": [100, 99, 98, np.nan],
        },
        index=dates,
    )
    events = pd.Series([0, 0, 0, 1], index=dates)

    mask = build_failure_to_fall_filter(features, lookback=2, min_factor_drawdown=0.01)
    filtered = apply_failure_to_fall_filter(events, mask)

    assert bool(mask.iloc[3]) is False
    assert filtered.iloc[3] == 0


def test_compare_failure_to_fall_filter_reports_base_and_filtered_metrics():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    frame = pd.DataFrame(
        {
            "High": [101, 102, 103, 102, 103, 91],
            "Low": [99, 100, 101, 100, 101, 89],
            "Close": [100, 101, 102, 101, 102, 90],
        },
        index=dates,
    )
    features = pd.DataFrame(
        {
            "close": [100, 101, 102, 101, 102, 90],
            "benchmark_close": [100, 100, 100, 96, 97, 90],
        },
        index=dates,
    )
    events = pd.Series([0, 0, 0, 1, -1, 1], index=dates)

    comparison = compare_failure_to_fall_filter(
        frame,
        features,
        events,
        lookback=3,
        min_factor_drawdown=0.03,
        max_asset_drawdown=0.03,
    )

    assert comparison["passed_buy_count"] == 1
    assert comparison["blocked_buy_count"] == 1
    assert comparison["base"]["trade_count"] >= comparison["filtered"]["trade_count"]
    assert "total_return" in comparison["filtered"]


def test_evaluate_signal_events_reports_standalone_metrics():
    frame = pd.DataFrame(
        {
            "High": [100, 101, 111, 122],
            "Low": [99, 99, 109, 120],
            "Close": [100, 100, 110, 121],
        }
    )
    events = pd.Series([1, 0, -1, 0], index=frame.index)

    metrics = evaluate_signal_events(frame, events)

    assert metrics["trade_count"] == 2.0
    assert metrics["signal_exit_count"] == 1.0
    assert metrics["total_return"] > 0
    assert "sharpe" in metrics


def test_compare_atr_stop_variants_reports_no_stop_and_stop_metrics():
    frame = pd.DataFrame(
        {
            "High": [100, 102, 103, 100, 101],
            "Low": [99, 100, 101, 90, 99],
            "Close": [100, 101, 102, 95, 100],
        }
    )
    events = pd.Series([1, 0, 0, 0, 0], index=frame.index)

    variants = compare_atr_stop_variants(frame, events, multipliers=[1.0])

    assert [variant["variant"] for variant in variants] == ["no_atr_stop", "atr_stop_1"]
    assert variants[0]["atr_stop_multiplier"] is None
    assert variants[1]["atr_stop_multiplier"] == 1.0
    assert variants[1]["atr_stop_exit_count"] == 1.0
