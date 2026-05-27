import random
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.optimization.genetic import GeneticOptimizer


class TestGeneticOptimizer(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({"Close": [100, 101, 102]})
        self.optimizer = GeneticOptimizer(self.df, population_size=10, generations=2)

    @patch("src.optimization.evaluator.StrategyEvaluator.evaluate")
    def test_optimization_run(self, mock_evaluate):
        """유전 알고리즘 실행 시 logbook까지 함께 반환한다."""
        mock_evaluate.side_effect = (
            lambda df, params, strategy_type="MACD_RSI": (random.random(),)
        )

        best_params, best_fitness, logbook = self.optimizer.run()

        self.assertIsInstance(best_params, list)
        self.assertIsInstance(best_fitness, float)
        self.assertEqual(len(best_params), 6)
        self.assertIsNotNone(logbook)
        self.assertIn("best_params", logbook[0])
        self.assertEqual(len(logbook[0]["best_params"]), 6)
        self.assertGreater(mock_evaluate.call_count, 10)

    def test_dashboard_style_init_supports_optional_dataframe(self):
        optimizer = GeneticOptimizer(population_size=12, generations=3, mutation_rate=0.35)

        self.assertIsNone(optimizer.df)
        self.assertEqual(optimizer.pop_size, 12)
        self.assertEqual(optimizer.ngen, 3)
        self.assertAlmostEqual(optimizer.mutation_rate, 0.35)
        self.assertTrue(optimizer.evaluator.use_regime_filter)

    def test_evolve_requires_dataframe_when_none_loaded(self):
        optimizer = GeneticOptimizer(population_size=8, generations=2)

        with self.assertRaises(ValueError):
            optimizer.evolve(symbol="005930")

    def test_run_returns_consistent_error_tuple_for_empty_dataframe(self):
        optimizer = GeneticOptimizer(pd.DataFrame(), population_size=8, generations=2)

        best_params, best_fitness, logbook = optimizer.run()

        self.assertEqual(best_params, [])
        self.assertEqual(best_fitness, 0.0)
        self.assertIsNone(logbook)

    def test_evolve_returns_dashboard_result_shape(self):
        optimizer = GeneticOptimizer(self.df, population_size=10, generations=2, mutation_rate=0.25)
        mock_logbook = MagicMock()
        mock_logbook.select.return_value = [1.0, 1.1, 1.23]
        optimizer.run = MagicMock(return_value=([5, 26, 9, 14, 30, 70], 1.23, mock_logbook))

        result = optimizer.evolve(symbol="005930")

        self.assertEqual(result["symbol"], "005930")
        self.assertEqual(result["best_params"], [5, 26, 9, 14, 30, 70])
        self.assertEqual(result["best_fitness"], 1.23)
        self.assertEqual(result["population_size"], 10)
        self.assertEqual(result["generations"], 2)
        self.assertEqual(result["mutation_rate"], 0.25)
        self.assertEqual(result["history"], [1.0, 1.1, 1.23])
        self.assertIn("use_regime_filter", result)
        self.assertIn("regime_config", result)
        self.assertIn("risk_config", result)

    def test_evolve_uses_requested_strategy_type_and_parameter_labels(self):
        optimizer = GeneticOptimizer(
            self.df,
            population_size=10,
            generations=2,
            mutation_rate=0.25,
            strategy_type="MA Crossover",
        )
        mock_logbook = MagicMock()
        mock_logbook.select.return_value = [0.5, 0.75]
        optimizer.run = MagicMock(return_value=([5, 20], 0.75, mock_logbook))

        result = optimizer.evolve(symbol="AAPL")

        self.assertEqual(result["strategy_type"], "MA_CROSSOVER")
        self.assertEqual(result["parameter_labels"], ["Short Window", "Long Window"])
        self.assertEqual(result["best_parameters"], {"Short Window": 5, "Long Window": 20})

    def test_evolve_exposes_resilient_reclaim_parameters(self):
        optimizer = GeneticOptimizer(
            self.df,
            population_size=10,
            generations=2,
            mutation_rate=0.25,
            strategy_type="Resilient Reclaim",
        )
        optimizer.run = MagicMock(return_value=([126, 20, 10, 9700, 0, 9700], 0.42, None))

        result = optimizer.evolve(symbol="005930")

        self.assertEqual(result["strategy_type"], "RESILIENT_RECLAIM")
        self.assertEqual(result["strategy_display_name"], "Resilient Reclaim")
        self.assertEqual(
            result["best_parameters"],
            {
                "High Window": 126,
                "Momentum Window": 20,
                "Reclaim Lookback": 10,
                "High Proximity bps": 9700,
                "Min Residual Momentum bps": 0,
                "Failure Buffer bps": 9700,
            },
        )

    def test_evolve_can_attach_validation_result(self):
        optimizer = GeneticOptimizer(
            self.df,
            population_size=10,
            generations=2,
            strategy_type="MA Crossover",
        )
        optimizer.run = MagicMock(return_value=([5, 20], 0.75, None))
        optimizer.evaluator.evaluate_validation = MagicMock(
            return_value={"method": "train_test", "test": {"fitness": 0.6}}
        )

        result = optimizer.evolve(
            symbol="AAPL",
            validation_method="train_test",
            validation_kwargs={"train_ratio": 0.7},
        )

        self.assertEqual(result["validation"]["method"], "train_test")
        optimizer.evaluator.evaluate_validation.assert_called_once()

    def test_evolve_records_generation_level_validation_curve(self):
        optimizer = GeneticOptimizer(
            self.df,
            population_size=10,
            generations=2,
            strategy_type="MA Crossover",
        )
        optimizer.run = MagicMock(
            return_value=(
                [5, 20],
                0.75,
                [
                    {"gen": 0, "max": 0.5, "best_params": [3, 18]},
                    {"gen": 1, "max": 0.75, "best_params": [5, 20]},
                ],
            )
        )

        def fake_validation(df, params, **kwargs):
            test_fitness = float(params[0]) / 10.0
            return {
                "method": "train_test",
                "train": {"fitness": test_fitness + 0.1},
                "test": {"fitness": test_fitness},
            }

        optimizer.evaluator.evaluate_validation = MagicMock(side_effect=fake_validation)

        result = optimizer.evolve(
            symbol="AAPL",
            validation_method="train_test",
            validation_kwargs={"train_ratio": 0.7},
        )

        generation_history = result["validation"]["generation_history"]
        self.assertEqual(
            generation_history,
            [
                {
                    "generation": 0,
                    "fitness": 0.5,
                    "params": [3, 18],
                    "train_fitness": 0.4,
                    "test_fitness": 0.3,
                },
                {
                    "generation": 1,
                    "fitness": 0.75,
                    "params": [5, 20],
                    "train_fitness": 0.6,
                    "test_fitness": 0.5,
                },
            ],
        )
        self.assertEqual(optimizer.evaluator.evaluate_validation.call_count, 2)

    def test_evolve_supports_legacy_run_return_without_logbook(self):
        optimizer = GeneticOptimizer(self.df, population_size=10, generations=2, mutation_rate=0.25)
        optimizer.run = MagicMock(return_value=([5, 26, 9, 14, 30, 70], 1.23))

        result = optimizer.evolve(symbol="005930")

        self.assertEqual(result["history"], [1.23])


if __name__ == "__main__":
    unittest.main()
