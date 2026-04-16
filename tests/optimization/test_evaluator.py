import unittest
import pandas as pd
import numpy as np
from src.optimization.evaluator import StrategyEvaluator

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

if __name__ == '__main__':
    unittest.main()
