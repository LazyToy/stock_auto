"""Unit Tests for New Features (Mocked)
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# Adjust path for execution
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.analysis.sentiment import SentimentAnalyzer
from src.utils.notification import send_notification
from src.portfolio.optimizer import PortfolioOptimizer
from src.strategies.ml_strategy import RandomForestStrategy, MLPrediction

class TestSentimentAnalyzer(unittest.TestCase):
    def test_analyze_with_llm_mock(self):

        # Setup mock
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "0.75"  # Mocked positive score
        mock_model.generate_content.return_value = mock_response
    
        analyzer = SentimentAnalyzer()
        analyzer.gemini_model = mock_model # Inject mock
        
        titles = ["Company reports record profits", "New partnership announced"]
        score = analyzer._analyze_with_llm(titles)
        
        self.assertEqual(score, 0.75)
        mock_model.generate_content.assert_called_once()

    def test_analyze_with_llm_negative(self):

        # Setup mock
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "-0.9"  # Mocked negative score
        mock_model.generate_content.return_value = mock_response
    
        analyzer = SentimentAnalyzer()
        analyzer.gemini_model = mock_model 
        
        titles = ["CEO arrested for fraud", "Stock plummets 20%"]
        score = analyzer._analyze_with_llm(titles)
        
        self.assertEqual(score, -0.9)

class TestNotification(unittest.TestCase):
    @patch('requests.post')
    def test_send_discord_notification(self, mock_post):
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response
        
        # Test
        from src.config import Config
        Config.DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/dummy"
        
        result = send_notification("Test Message")
        
        # Check result
        self.assertTrue(result)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://discord.com/api/webhooks/dummy")
        self.assertIn("Test Message", kwargs['data'])

class TestPortfolioOptimizer(unittest.TestCase):
    def setUp(self):
        # Create dummy returns data
        dates = pd.date_range(start='2024-01-01', periods=100)
        data = {
            'A': np.random.normal(0.001, 0.02, 100),
            'B': np.random.normal(0.0005, 0.01, 100)
        }
        self.df = pd.DataFrame(data, index=dates)

    def test_optimize_sharpe_ratio(self):
        optimizer = PortfolioOptimizer(self.df)
        weights = optimizer.optimize_sharpe_ratio()
        
        self.assertIsInstance(weights, dict)
        self.assertIsInstance(weights, dict)
        self.assertGreaterEqual(len(weights), 1)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)


    def test_optimize_min_variance(self):
        optimizer = PortfolioOptimizer(self.df)
        weights = optimizer.optimize_min_variance()
        
        self.assertIsInstance(weights, dict)
        self.assertIsInstance(weights, dict)
        self.assertGreaterEqual(len(weights), 1)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)


class TestMLStrategy(unittest.TestCase):
    def setUp(self):
        # Create dummy OHLCV data for training
        dates = pd.date_range(start='2024-01-01', periods=200)
        data = {
            'open': np.random.uniform(100, 200, 200),
            'high': np.random.uniform(100, 200, 200),
            'low': np.random.uniform(100, 200, 200),
            'close': np.random.uniform(100, 200, 200),
            'volume': np.random.randint(1000, 10000, 200)
        }
        self.df = pd.DataFrame(data, index=dates)
        
        # Ensure high >= low
        self.df['high'] = self.df[['open', 'close', 'high']].max(axis=1)
        self.df['low'] = self.df[['open', 'close', 'low']].min(axis=1)

    def test_rf_training_and_prediction(self):
        strategy = RandomForestStrategy(n_estimators=10, lookback=20)
        
        # Train
        accuracy = strategy.train(self.df)
        self.assertTrue(0.0 <= accuracy <= 1.0)
        self.assertTrue(strategy.is_trained)
        
        # Predict
        prediction = strategy.predict(self.df)
        self.assertIsInstance(prediction, MLPrediction)
        self.assertIn(prediction.signal, [-1, 0, 1])
        self.assertTrue(0.0 <= prediction.probability <= 1.0)
        
        # Feature Importance
        importances = strategy.get_feature_importances()
        self.assertIsInstance(importances, dict)
        self.assertGreater(len(importances), 0)

if __name__ == '__main__':
    unittest.main()
