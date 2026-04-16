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
        self.assertGreater(mock_evaluate.call_count, 10)

    def test_dashboard_style_init_supports_optional_dataframe(self):
        optimizer = GeneticOptimizer(population_size=12, generations=3, mutation_rate=0.35)

        self.assertIsNone(optimizer.df)
        self.assertEqual(optimizer.pop_size, 12)
        self.assertEqual(optimizer.ngen, 3)
        self.assertAlmostEqual(optimizer.mutation_rate, 0.35)

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

    def test_evolve_supports_legacy_run_return_without_logbook(self):
        optimizer = GeneticOptimizer(self.df, population_size=10, generations=2, mutation_rate=0.25)
        optimizer.run = MagicMock(return_value=([5, 26, 9, 14, 30, 70], 1.23))

        result = optimizer.evolve(symbol="005930")

        self.assertEqual(result["history"], [1.23])


if __name__ == "__main__":
    unittest.main()
