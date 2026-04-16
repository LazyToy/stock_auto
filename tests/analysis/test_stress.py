import unittest
from unittest import mock
import pandas as pd
import numpy as np
from src.analysis.stress import StressTester, Scenario

class TestStressTester(unittest.TestCase):
    def setUp(self):
        self.tester = StressTester()
        
    def test_calculate_risk_metrics(self):
        """리스크 지표 계산 테스트 (VaR, MaxDD)"""
        # Create dummy returns: Normal distribution
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0, 0.01, 100))
        # Introduce a large loss for MaxDD
        returns.iloc[50] = -0.05
        
        metrics = self.tester.calculate_risk_metrics(returns)
        
        self.assertIn('VaR_95', metrics)
        self.assertIn('VaR_99', metrics)
        self.assertIn('Max_Drawdown', metrics)
        
        # VaR should be negative
        self.assertLess(metrics['VaR_95'], 0)
        
    def test_simulate_scenario_logic(self):
        """시나리오 시뮬레이션 로직 테스트"""
        # Portfolio: 50% Asset A, 50% Asset B
        portfolio = {'A': 0.5, 'B': 0.5}
        total_value = 10000
        
        # Scenario Data (Mock): A dropped 10%, B dropped 20%
        # We need to mock the data fetching part.
        # Let's assume simulate_scenario accepts a custom return map for testing
        
        scenario_returns = {
            'A': -0.10,
            'B': -0.20
        }
        
        # Expected Loss: 0.5 * -10% + 0.5 * -20% = -15%
        # -15% of 10000 = -1500
        
        impact = self.tester._calculate_impact(portfolio, total_value, scenario_returns)
        
        self.assertAlmostEqual(impact['total_loss_amount'], -1500)
        self.assertAlmostEqual(impact['portfolio_return'], -0.15)

    @mock.patch('yfinance.download')
    def test_simulate_scenario_error(self, mock_yf):
        """데이터 다운로드 실패 시 프록시 수익률로 폴백하는지 확인"""
        portfolio = {'A': 1.0}
        total_value = 10000
        mock_yf.side_effect = Exception("Mock DB locked")
        result = self.tester.simulate_scenario(portfolio, total_value, '2008_Financial_Crisis')
        self.assertNotIn("error", result)
        self.assertTrue(result["proxy_used"])
        self.assertAlmostEqual(result["portfolio_return"], -0.30)
        self.assertAlmostEqual(result["total_loss_amount"], -3000)


if __name__ == '__main__':
    unittest.main()
