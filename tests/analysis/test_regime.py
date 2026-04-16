import unittest
import numpy as np
import pandas as pd
import os
from unittest.mock import MagicMock, patch
from src.analysis.regime import RegimeDetector

class TestRegimeDetector(unittest.TestCase):
    def setUp(self):
        self.detector = RegimeDetector(n_components=3)
        # Create dummy data for testing
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        self.dummy_data = pd.DataFrame({
            'daily_return': np.random.normal(0, 0.01, 100),
            'volatility': np.random.normal(0.01, 0.002, 100),
            'trend': np.random.normal(0, 0.05, 100)
        }, index=dates)

    def test_initialization(self):
        """초기화 테스트"""
        self.assertEqual(self.detector.n_components, 3)
        self.assertIsNotNone(self.detector.model)

    def test_train_model(self):
        """모델 학습 테스트"""
        # HMM training usually doesn't return anything, just updates internal state
        self.detector.train_model(self.dummy_data)
        self.assertTrue(hasattr(self.detector.model, 'monitor_'))
        self.assertTrue(self.detector.model.monitor_.converged)

    def test_predict_regime(self):
        """레짐 예측 테스트"""
        self.detector.train_model(self.dummy_data)
        
        # Predict on last row
        current_data = self.dummy_data.iloc[[-1]]
        regime = self.detector.predict_regime(current_data)
        
        self.assertIsInstance(regime, int)
        self.assertTrue(0 <= regime < 3)

    def test_save_load_model(self):
        """모델 저장 및 로드 테스트"""
        self.detector.train_model(self.dummy_data)
        
        save_path = "test_hmm_model.pkl"
        try:
            self.detector.save_model(save_path)
            self.assertTrue(os.path.exists(save_path))
            
            new_detector = RegimeDetector(n_components=3)
            new_detector.load_model(save_path)
            
            # Check if means are loaded (simple check)
            np.testing.assert_array_equal(self.detector.model.means_, new_detector.model.means_)
            
        finally:
            if os.path.exists(save_path):
                os.remove(save_path)

if __name__ == '__main__':
    unittest.main()
