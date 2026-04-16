import unittest
from unittest.mock import MagicMock, patch
from src.copilot.tools import get_portfolio_summary, get_recent_trades, explain_trade_decision

class TestCopilotTools(unittest.TestCase):
    def setUp(self):
        # Mock database and API client for tests
        self.mock_db = MagicMock()
        self.mock_api = MagicMock()
        
    @patch('src.copilot.tools.get_db')
    @patch('src.copilot.tools.KISAPIClient')
    def test_get_portfolio_summary(self, mock_api_cls, mock_get_db):
        """포트폴리오 요약 조회 테스트"""
        # Mock setup
        mock_client = mock_api_cls.return_value
        mock_client.get_balance.return_value = {
            'total_asset': 1000000,
            'deposit': 500000,
            'stocks': [
                {'symbol': '005930', 'name': '삼성전자', 'quantity': 10, 'current_price': 50000, 'avg_price': 48000, 'profit_rate': 4.16}
            ]
        }
        
        # LangChain Tool invocation
        result = get_portfolio_summary.invoke({})
        
        self.assertIn("총 자산: 1,000,000", result)
        self.assertIn("삼성전자", result)
        self.assertIn("10주", result)
        
    @patch('src.copilot.tools.get_db')
    def test_get_recent_trades(self, mock_get_db):
        """최근 거래 내역 조회 테스트"""
        mock_db = mock_get_db.return_value
        mock_db.get_trades.return_value = [
            {'timestamp': '2024-01-01 10:00:00', 'symbol': '005930', 'side': 'BUY', 'quantity': 5, 'price': 50000, 'reason': 'RSI < 30'}
        ]
        
        result = get_recent_trades.invoke({"limit": 1})
        
        self.assertIn("005930", result)
        self.assertIn("BUY", result)
        self.assertIn("RSI < 30", result)

    def test_explain_trade_decision(self):
        """매매 결정 이유 설명 테스트"""
        with patch('src.copilot.tools.get_db') as mock_get_db:
             mock_db = mock_get_db.return_value
             mock_db.get_trades.return_value = [
                 {'timestamp': '2024-01-01 10:00:00', 'symbol': '005930', 'side': 'BUY', 'reason': 'Macd Golden Cross'}
             ]
             
             result = explain_trade_decision.invoke({"symbol": "005930"})
             self.assertIn("Macd Golden Cross", result)

if __name__ == '__main__':
    unittest.main()
