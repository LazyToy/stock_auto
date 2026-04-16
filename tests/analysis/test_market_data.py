import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from src.analysis.market_data import MarketDataFetcher

class TestMarketDataFetcher(unittest.TestCase):
    def setUp(self):
        self.fetcher = MarketDataFetcher()
        
    @patch('yfinance.Ticker')
    def test_fetch_history_success(self, mock_ticker):
        """데이터 수집 성공 테스트"""
        # Mock yfinance data
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        mock_df = pd.DataFrame({
            'Close': np.linspace(100, 110, 10),
            'Volume': np.random.randint(1000, 2000, 10)
        }, index=dates)
        
        mock_ticker.return_value.history.return_value = mock_df
        
        df = self.fetcher.fetch_history('SPY', period='1mo')
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 10)
        self.assertIn('Close', df.columns)

    @patch('yfinance.Ticker')
    def test_calculate_features(self, mock_ticker):
        """파생 변수(수익률, 변동성) 계산 테스트"""
        # Need enough data for 50-day MA
        dates = pd.date_range(start='2024-01-01', periods=60, freq='D')
        mock_df = pd.DataFrame({
            'Close': np.linspace(100, 120, 60) # 상승 추세
        }, index=dates)
        
        df_features = self.fetcher.calculate_features(mock_df)
        
        self.assertIn('daily_return', df_features.columns)
        self.assertIn('volatility', df_features.columns)
        self.assertIn('trend', df_features.columns)
        
        # Check logic: Volatility should not be NaN (after window)
        self.assertFalse(df_features['volatility'].iloc[-1] == np.nan)

    def test_get_regime_indicators(self):
        """레짐 감지용 통합 지표 수집 테스트"""
        # This integration test mocks multiple calls (S&P500, VIX, etc.)
        with patch('yfinance.Ticker') as mock_ticker:
            # Create dummy DF with enough data for MA50
            dates = pd.date_range(start='2024-01-01', periods=60, freq='D')
            mock_df = pd.DataFrame({'Close': np.linspace(100, 110, 60)}, index=dates)
            
            # Configure mock to return this df for history calls
            mock_ticker.return_value.history.return_value = mock_df
            
            data = self.fetcher.get_regime_input_data()
            
            self.assertIsInstance(data, pd.DataFrame)
            self.assertFalse(data.empty)
            self.assertIn('daily_return', data.columns)

if __name__ == '__main__':
    unittest.main()
