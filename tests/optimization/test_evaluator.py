import unittest
import pandas as pd
import numpy as np
from src.optimization.evaluator import StrategyEvaluator
from src.optimization.regime import HIGH_VOLATILITY, RANGE, UPTREND, RegimeConfig
from src.optimization.risk import RiskConfig

class TestStrategyEvaluator(unittest.TestCase):
    def setUp(self):
        self.evaluator = StrategyEvaluator()
        
        # Create dummy data (uptrend)
        dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
        self.df = pd.DataFrame({
            'Close': np.linspace(100, 200, 100) + np.random.normal(0, 2, 100),
            'Volume': 1000
        }, index=dates)

    def test_evaluate_macd_rsi_simple(self):
        """MACD+RSI 전략 평가 테스트"""
        # MACD Params: fast=12, slow=26, signal=9
        # RSI Params: window=14, low=30, high=70
        params = [12, 26, 9, 14, 30, 70]
        
        fitness = self.evaluator.evaluate(self.df, params, strategy_type='MACD_RSI')
        
        # Fitness should be a tuple (Sharpe,)
        self.assertIsInstance(fitness, tuple)
        self.assertEqual(len(fitness), 1)
        self.assertIsInstance(fitness[0], float)

    def test_evaluate_invalid_params(self):
        """잘못된 파라미터 (Fast > Slow) 테스트"""
        # Fast(50) > Slow(20) -> Should return penalty fitness
        params = [50, 20, 9, 14, 30, 70]
        
        fitness = self.evaluator.evaluate(self.df, params, strategy_type='MACD_RSI')
        
        # Should be very low fitness (penalty)
        self.assertLess(fitness[0], 0)

    def test_evaluate_invalid_macd_rsi_thresholds(self):
        params = [12, 26, 9, 14, 80, 20]

        fitness = self.evaluator.evaluate(self.df, params, strategy_type="MACD_RSI")

        self.assertLess(fitness[0], 0)

    def test_rsi_handles_no_loss_uptrend_as_overbought(self):
        close = pd.Series([100, 101, 102, 103, 104, 105], dtype=float)

        rsi = self.evaluator._calculate_rsi(close, window=3)

        self.assertEqual(rsi.iloc[-1], 100.0)

    def test_evaluate_supports_dashboard_strategy_selection(self):
        """UI 전략 선택값이 실제 평가 전략으로 연결된다."""
        strategy_params = {
            "MA Crossover": [5, 20],
            "RSI": [14, 30, 70],
            "MACD": [12, 26, 9],
            "Bollinger Bands": [20, 20, 100],
            "Ensemble Vote": [1, 1],
            "Resilient Reclaim": [126, 20, 10, 9700, 0, 9700],
            "MACD_RSI": [12, 26, 9, 14, 30, 70],
        }

        for strategy_type, params in strategy_params.items():
            with self.subTest(strategy_type=strategy_type):
                fitness = self.evaluator.evaluate(
                    self.df,
                    params,
                    strategy_type=strategy_type,
                )

                self.assertIsInstance(fitness, tuple)
                self.assertEqual(len(fitness), 1)
                self.assertIsInstance(fitness[0], float)

    def test_evaluate_detailed_returns_risk_metrics_and_composite_fitness(self):
        """상세 평가는 Sharpe 외 리스크 지표와 composite fitness를 반환한다."""
        result = self.evaluator.evaluate_detailed(
            self.df,
            [5, 20],
            strategy_type="MA Crossover",
            fitness_metric="composite",
        )

        self.assertEqual(result.strategy_type, "MA_CROSSOVER")
        self.assertIsInstance(result.fitness, float)
        self.assertIn("sharpe", result.metrics)
        self.assertIn("max_drawdown", result.metrics)
        self.assertIn("trade_count", result.metrics)
        self.assertIn("turnover", result.metrics)
        self.assertLessEqual(result.metrics["max_drawdown"], 0.0)

    def test_evaluate_detailed_applies_risk_manager_exits(self):
        evaluator = StrategyEvaluator(risk_config=RiskConfig(max_holding_days=1))
        frame = pd.DataFrame(
            {
                "High": [100, 101, 102, 103, 104],
                "Low": [99, 98, 100, 101, 102],
                "Close": [100, 99, 101, 102, 103],
            }
        )

        result = evaluator.evaluate_detailed(
            frame,
            [1, 2],
            strategy_type="MA Crossover",
            fitness_metric="composite",
        )

        self.assertEqual(result.metrics["max_holding_exit_count"], 1.0)

    def test_evaluate_detailed_can_apply_regime_filter(self):
        evaluator = StrategyEvaluator(
            use_regime_filter=True,
            regime_config=RegimeConfig(
                short_window=2,
                long_window=4,
                adx_trend_threshold=0,
                high_volatility_threshold=999,
            ),
        )
        frame = pd.DataFrame(
            {
                "High": [101, 96, 91, 86, 81, 76, 71, 66, 61, 56],
                "Low": [99, 94, 89, 84, 79, 74, 69, 64, 59, 54],
                "Close": [100, 95, 90, 85, 80, 75, 70, 65, 60, 55],
                "Volume": 1000,
            }
        )

        result = evaluator.evaluate_detailed(
            frame,
            [3, 30, 70],
            strategy_type="RSI",
            fitness_metric="composite",
        )

        self.assertGreater(result.metrics["regime_blocked_buy_count"], 0.0)
        self.assertEqual(result.metrics["trade_count"], 0.0)

    def test_resilient_reclaim_strategy_generates_reclaim_trade(self):
        frame = pd.DataFrame(
            {
                "High": [101, 111, 107, 105, 113, 114, 115],
                "Low": [99, 109, 105, 103, 111, 112, 113],
                "Close": [100, 110, 106, 104, 112, 113, 114],
                "Volume": 1000,
            }
        )

        result = self.evaluator.evaluate_detailed(
            frame,
            [4, 2, 3, 9800, 100, 9700],
            strategy_type="Resilient Reclaim",
            fitness_metric="composite",
        )

        self.assertEqual(result.strategy_type, "RESILIENT_RECLAIM")
        self.assertGreaterEqual(result.metrics["trade_count"], 1.0)
        self.assertIsInstance(result.fitness, float)

    def test_build_signal_events_exposes_resilient_reclaim_events_for_monitors(self):
        frame = pd.DataFrame(
            {
                "High": [101, 111, 107, 105, 113],
                "Low": [99, 109, 105, 103, 111],
                "Close": [100, 110, 106, 104, 112],
                "Volume": 1000,
            }
        )

        events = self.evaluator.build_signal_events(
            frame,
            [4, 2, 3, 9800, 100, 9700],
            strategy_type="Resilient Reclaim",
        )

        self.assertEqual(events.iloc[-1], 1)

    def test_resilient_reclaim_rejects_invalid_thresholds(self):
        fitness = self.evaluator.evaluate(
            self.df,
            [20, 20, 10, 9700, 0, 10500],
            strategy_type="Resilient Reclaim",
        )

        self.assertLess(fitness[0], 0)

    def test_evaluate_with_train_test_split_reports_out_of_sample_metrics(self):
        """train/test split 검증은 train과 test metrics를 분리해서 반환한다."""
        result = self.evaluator.evaluate_validation(
            self.df,
            [5, 20],
            strategy_type="MA Crossover",
            validation_method="train_test",
            train_ratio=0.7,
        )

        self.assertEqual(result["method"], "train_test")
        self.assertIn("train", result)
        self.assertIn("test", result)
        self.assertIn("fitness", result["train"])
        self.assertIn("fitness", result["test"])
        self.assertIn("overfit_guard", result)
        self.assertIn("deflated_sharpe", result["overfit_guard"])
        self.assertIn("passes", result["overfit_guard"])

    def test_walk_forward_validation_reports_each_fold(self):
        """walk-forward 검증은 fold별 out-of-sample 결과를 반환한다."""
        result = self.evaluator.evaluate_validation(
            self.df,
            [5, 20],
            strategy_type="MA Crossover",
            validation_method="walk_forward",
            train_window=40,
            test_window=20,
        )

        self.assertEqual(result["method"], "walk_forward")
        self.assertGreaterEqual(result["fold_count"], 2)
        self.assertEqual(len(result["folds"]), result["fold_count"])
        self.assertIn("aggregate", result)
        self.assertIn("overfit_guard", result)
        self.assertIn("stability_score", result["aggregate"])
        self.assertIn("test_fitness_std", result["aggregate"])

    def test_event_strategy_validation_rebuilds_events_per_train_test_slice(self):
        calls = []

        def event_builder(frame):
            calls.append((frame.index[0], len(frame)))
            events = pd.Series(0, index=frame.index)
            events.iloc[0] = 1
            events.iloc[-2] = -1
            return events

        result = self.evaluator.evaluate_event_strategy_validation(
            self.df.iloc[:10],
            event_builder,
            validation_method="train_test",
            train_ratio=0.6,
        )

        self.assertEqual(result["method"], "train_test")
        self.assertEqual([length for _, length in calls], [6, 4])
        self.assertIn("train", result)
        self.assertIn("test", result)
        self.assertIn("overfit_guard", result)

    def test_event_strategy_walk_forward_reports_fold_metrics(self):
        calls = []

        def event_builder(frame):
            calls.append(len(frame))
            events = pd.Series(0, index=frame.index)
            events.iloc[0] = 1
            events.iloc[-2] = -1
            return events

        result = self.evaluator.evaluate_event_strategy_validation(
            self.df.iloc[:12],
            event_builder,
            validation_method="walk_forward",
            train_window=4,
            test_window=4,
        )

        self.assertEqual(result["method"], "walk_forward")
        self.assertEqual(result["fold_count"], 2)
        self.assertEqual(calls, [4, 4, 4, 4])
        self.assertIn("aggregate", result)
        self.assertIn("overfit_guard", result)

    def test_overfit_guard_fails_when_trade_count_is_too_low(self):
        result = self.evaluator.evaluate_validation(
            self.df,
            [5, 20],
            strategy_type="MA Crossover",
            validation_method="train_test",
            min_trades=999,
        )

        self.assertFalse(result["overfit_guard"]["passes"])
        self.assertIn("min_trades", result["overfit_guard"]["failed_checks"])

    def test_ensemble_vote_returns_detailed_result(self):
        result = self.evaluator.evaluate_detailed(
            self.df,
            [1, 1],
            strategy_type="Ensemble Vote",
            fitness_metric="composite",
        )

        self.assertEqual(result.strategy_type, "ENSEMBLE_VOTE")
        self.assertIsInstance(result.fitness, float)
        self.assertIn("trade_count", result.metrics)

    def test_ensemble_vote_rejects_invalid_vote_thresholds(self):
        fitness = self.evaluator.evaluate(
            self.df,
            [0, 3],
            strategy_type="Ensemble Vote",
        )

        self.assertLess(fitness[0], 0)

    def test_ensemble_vote_rejects_fractional_vote_thresholds(self):
        fitness = self.evaluator.evaluate(
            self.df,
            [1.9, 1.0],
            strategy_type="Ensemble Vote",
        )

        self.assertLess(fitness[0], 0)

    def test_ensemble_vote_threshold_requires_enough_component_votes(self):
        close = pd.Series([100, 101, 102], dtype=float)
        evaluator = StrategyEvaluator()
        evaluator._ma_crossover_events = lambda close, params: pd.Series([1, 0, 1], index=close.index)
        evaluator._macd_events = lambda close, params: pd.Series([0, 1, 1], index=close.index)
        evaluator._rsi_events = lambda close, params: pd.Series([0, 0, 0], index=close.index)
        evaluator._bollinger_events = lambda close, params: pd.Series([0, 0, 0], index=close.index)

        events = evaluator._ensemble_vote_events(close, [2, 1])

        self.assertEqual(events.tolist(), [0, 0, 1])

    def test_ensemble_vote_regime_filter_keeps_component_regime_rules(self):
        close = pd.Series([100, 101, 102], dtype=float)
        regimes = pd.Series([RANGE, RANGE, HIGH_VOLATILITY], index=close.index)
        evaluator = StrategyEvaluator()
        evaluator._ma_crossover_events = lambda close, params: pd.Series([1, 0, -1], index=close.index)
        evaluator._macd_events = lambda close, params: pd.Series([0, 0, 0], index=close.index)
        evaluator._rsi_events = lambda close, params: pd.Series([0, 1, 0], index=close.index)
        evaluator._bollinger_events = lambda close, params: pd.Series([0, 0, 0], index=close.index)

        events = evaluator._ensemble_vote_events(close, [1, 1], regimes=regimes)

        self.assertEqual(events.tolist(), [0, 1, -1])

if __name__ == '__main__':
    unittest.main()
