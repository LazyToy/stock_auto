import json

import pandas as pd

from src.optimization.automl_runtime import (
    apply_automl_candidate_adjustment,
    load_automl_artifacts,
    save_automl_result,
)


def test_save_and_load_automl_result_artifact(tmp_path):
    result = {
        "symbol": "AAPL",
        "resolved_symbol": "AAPL",
        "strategy_type": "MA_CROSSOVER",
        "best_params": [5, 20],
        "best_fitness": 1.2,
        "validation": {"method": "train_test", "test": {"fitness": 0.8}},
    }

    path = save_automl_result(result, base_dir=tmp_path)
    loaded = load_automl_artifacts([path])

    assert path.exists()
    assert loaded[0]["symbol"] == "AAPL"
    assert loaded[0]["strategy_type"] == "MA_CROSSOVER"


def test_apply_automl_candidate_adjustment_adds_bounded_bonus():
    candidates = pd.DataFrame(
        [
            {"ticker": "AAPL", "score": 1.1},
            {"ticker": "MSFT", "score": 1.2},
        ]
    )
    artifacts = [
        {
            "symbol": "AAPL",
            "best_fitness": 2.0,
            "strategy_type": "MACD_RSI",
            "validation": {"test": {"fitness": 1.0}},
        }
    ]

    adjusted = apply_automl_candidate_adjustment(
        candidates,
        artifacts,
        min_fitness=0.5,
        max_bonus=0.3,
    )

    assert adjusted.loc[0, "automl_strategy"] == "MACD_RSI"
    assert adjusted.loc[0, "automl_fitness"] == 2.0
    assert adjusted.loc[0, "score"] == 1.4
    assert pd.isna(adjusted.loc[1, "automl_strategy"])
    assert adjusted.loc[1, "score"] == 1.2


def test_apply_automl_candidate_adjustment_skips_failed_overfit_guard():
    candidates = pd.DataFrame([{"ticker": "AAPL", "score": 1.1}])
    artifacts = [
        {
            "symbol": "AAPL",
            "best_fitness": 2.0,
            "strategy_type": "MACD_RSI",
            "validation": {
                "test": {"fitness": 1.5},
                "overfit_guard": {"passes": False, "failed_checks": ["min_trades"]},
            },
        }
    ]

    adjusted = apply_automl_candidate_adjustment(
        candidates,
        artifacts,
        min_fitness=0.5,
        max_bonus=0.3,
    )

    assert adjusted.loc[0, "score"] == 1.1
    assert pd.isna(adjusted.loc[0, "automl_strategy"])


def test_apply_automl_candidate_adjustment_uses_best_usable_artifact_per_symbol():
    candidates = pd.DataFrame([{"ticker": "AAPL", "score": 1.0}])
    artifacts = [
        {
            "symbol": "AAPL",
            "best_fitness": 1.0,
            "strategy_type": "MA_CROSSOVER",
            "validation": {"test": {"fitness": 0.8}},
        },
        {
            "symbol": "AAPL",
            "best_fitness": 5.0,
            "strategy_type": "MACD_RSI",
            "validation": {
                "test": {"fitness": 3.0},
                "overfit_guard": {"passes": False},
            },
        },
        {
            "symbol": "AAPL",
            "best_fitness": 2.0,
            "strategy_type": "ENSEMBLE_VOTE",
            "validation": {"test": {"fitness": 1.5}},
        },
    ]

    adjusted = apply_automl_candidate_adjustment(
        candidates,
        artifacts,
        min_fitness=0.5,
        max_bonus=0.3,
    )

    assert adjusted.loc[0, "automl_strategy"] == "ENSEMBLE_VOTE"
    assert adjusted.loc[0, "automl_validation_fitness"] == 1.5
    assert adjusted.loc[0, "score"] == 1.3


def test_apply_automl_candidate_adjustment_matches_raw_kr_ticker_to_resolved_artifact():
    candidates = pd.DataFrame([{"ticker": "005930", "score": 1.0}])
    artifacts = [
        {
            "symbol": "005930.KS",
            "requested_symbol": "005930",
            "resolved_symbol": "005930.KS",
            "best_fitness": 1.0,
            "strategy_type": "ENSEMBLE_VOTE",
            "validation": {"test": {"fitness": 0.8}},
        }
    ]

    adjusted = apply_automl_candidate_adjustment(
        candidates,
        artifacts,
        min_fitness=0.5,
        max_bonus=0.3,
    )

    assert adjusted.loc[0, "automl_strategy"] == "ENSEMBLE_VOTE"
    assert adjusted.loc[0, "score"] == 1.24


def test_load_automl_artifacts_skips_invalid_files(tmp_path):
    valid = tmp_path / "valid.json"
    invalid = tmp_path / "invalid.json"
    valid.write_text(json.dumps({"symbol": "AAPL", "best_fitness": 1.0}), encoding="utf-8")
    invalid.write_text("{not json", encoding="utf-8")

    loaded = load_automl_artifacts([valid, invalid])

    assert loaded == [{"symbol": "AAPL", "best_fitness": 1.0}]
