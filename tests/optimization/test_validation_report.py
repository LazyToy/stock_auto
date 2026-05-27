import json

from src.optimization.validation_report import (
    build_multi_symbol_validation_report,
    save_multi_symbol_validation_report,
)


def test_build_multi_symbol_validation_report_ranks_guard_passes_first():
    report = build_multi_symbol_validation_report(
        [
            {
                "symbol": "PASS",
                "strategy_type": "MA_CROSSOVER",
                "best_fitness": 1.2,
                "validation": {
                    "method": "walk_forward",
                    "aggregate": {
                        "average_test_fitness": 0.8,
                        "stability_score": 0.4,
                    },
                    "overfit_guard": {"passes": True, "failed_checks": []},
                },
            },
            {
                "symbol": "FAIL",
                "strategy_type": "MACD_RSI",
                "best_fitness": 2.0,
                "validation": {
                    "method": "walk_forward",
                    "aggregate": {
                        "average_test_fitness": 1.5,
                        "stability_score": 0.7,
                    },
                    "overfit_guard": {
                        "passes": False,
                        "failed_checks": ["fold_dispersion"],
                    },
                },
            },
            {"symbol": "EMPTY", "strategy_type": "RSI", "best_fitness": 0.5},
        ]
    )

    assert report["symbol_count"] == 3
    assert report["validated_symbol_count"] == 2
    assert report["guard_pass_count"] == 1
    assert report["guard_fail_count"] == 1
    assert report["best_usable_symbol"] == "PASS"
    assert report["average_validation_fitness"] == 1.15
    assert report["average_usable_validation_fitness"] == 0.8
    assert report["ranked_results"][0]["symbol"] == "PASS"
    assert report["ranked_results"][0]["usable"] is True
    assert report["ranked_results"][1]["symbol"] == "FAIL"
    assert report["ranked_results"][1]["usable"] is False
    assert report["ranked_results"][1]["overfit_failed_checks"] == ["fold_dispersion"]


def test_build_multi_symbol_validation_report_supports_train_test_shape():
    report = build_multi_symbol_validation_report(
        [
            {
                "symbol": "AAPL",
                "resolved_symbol": "AAPL",
                "strategy_type": "ENSEMBLE_VOTE",
                "best_fitness": 1.0,
                "validation": {
                    "method": "train_test",
                    "test": {
                        "fitness": 0.6,
                        "metrics": {"trade_count": 4, "sharpe": 0.7},
                    },
                    "overfit_guard": {"passes": True, "deflated_sharpe": 0.5},
                },
            }
        ]
    )

    entry = report["ranked_results"][0]
    assert entry["symbol"] == "AAPL"
    assert entry["strategy_type"] == "ENSEMBLE_VOTE"
    assert entry["validation_method"] == "train_test"
    assert entry["validation_fitness"] == 0.6
    assert entry["test_trade_count"] == 4.0
    assert entry["deflated_sharpe"] == 0.5


def test_multi_symbol_report_preserves_resilient_reclaim_strategy():
    report = build_multi_symbol_validation_report(
        [
            {
                "symbol": "005930.KS",
                "requested_symbol": "005930",
                "resolved_symbol": "005930.KS",
                "strategy_type": "RESILIENT_RECLAIM",
                "strategy_display_name": "Resilient Reclaim",
                "best_fitness": 1.2,
                "validation": {
                    "method": "walk_forward",
                    "aggregate": {
                        "average_test_fitness": 0.7,
                        "stability_score": 0.5,
                    },
                    "overfit_guard": {"passes": True, "failed_checks": []},
                },
            }
        ],
        requested_symbols=["005930"],
    )

    entry = report["ranked_results"][0]
    assert entry["symbol"] == "005930.KS"
    assert entry["strategy_type"] == "RESILIENT_RECLAIM"
    assert entry["usable"] is True
    assert report["best_usable_symbol"] == "005930.KS"


def test_save_multi_symbol_validation_report_writes_json(tmp_path):
    report = build_multi_symbol_validation_report(
        [
            {
                "symbol": "AAPL",
                "strategy_type": "MA_CROSSOVER",
                "best_fitness": 1.0,
                "validation": {"test": {"fitness": 0.6}},
            }
        ]
    )

    path = save_multi_symbol_validation_report(report, base_dir=tmp_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent == tmp_path / "data" / "automl_reports"
    assert loaded["validated_symbol_count"] == 1
    assert loaded["ranked_results"][0]["symbol"] == "AAPL"


def test_build_multi_symbol_validation_report_counts_requested_and_skipped_symbols():
    report = build_multi_symbol_validation_report(
        [
            {
                "symbol": "AAPL",
                "strategy_type": "MA_CROSSOVER",
                "validation": {"test": {"fitness": 0.6}},
            },
            {
                "symbol": "005930",
                "status": "skipped",
                "error": "No data found",
            },
        ],
        requested_symbols=["AAPL", "005930", "MSFT"],
    )

    assert report["symbol_count"] == 3
    assert report["result_count"] == 2
    assert report["validated_symbol_count"] == 1
    assert report["skipped_symbol_count"] == 1
    assert report["missing_symbol_count"] == 1
    assert report["skipped_results"][0]["symbol"] == "005930"
    assert report["missing_symbols"] == ["MSFT"]


def test_build_multi_symbol_validation_report_matches_requested_and_resolved_symbols():
    report = build_multi_symbol_validation_report(
        [
            {
                "symbol": "005930.KS",
                "requested_symbol": "005930",
                "resolved_symbol": "005930.KS",
                "strategy_type": "ENSEMBLE_VOTE",
                "validation": {"test": {"fitness": 0.7}},
            }
        ],
        requested_symbols=["005930"],
    )

    assert report["symbol_count"] == 1
    assert report["missing_symbol_count"] == 0
    assert report["missing_symbols"] == []
    assert report["ranked_results"][0]["requested_symbol"] == "005930"
    assert report["ranked_results"][0]["symbol"] == "005930.KS"


def test_save_multi_symbol_validation_report_uses_unique_filenames(tmp_path):
    report = build_multi_symbol_validation_report([])

    first = save_multi_symbol_validation_report(report, base_dir=tmp_path)
    second = save_multi_symbol_validation_report(report, base_dir=tmp_path)

    assert first != second
