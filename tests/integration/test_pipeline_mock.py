"""Integration Test with Mocks (Offline)

This script simulates the entire data flow without connecting to external APIs.
1. Data collection (Mocked)
2. Sentiment Analysis (Mocked)
3. Portfolio Optimization
4. Order Generation
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# Adjust path for execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.selector import StockSelector
from src.analysis.sentiment import SentimentAnalyzer
from src.trader.auto_trader import AutoTrader
from src.data.api_client import KISAPIClient
from src.data.models import Account, Position

class TestAutoTradingPipeline(unittest.TestCase):
    
    @patch('src.data.api_client.KISAPIClient')
    def test_full_pipeline(self, MockAPIClient):
        print("\n--- Starting Full Pipeline Integration Test (Mocked) ---")
        
        # 1. Setup Mock API Client
        api_client = MockAPIClient()
        
        # Mock Balance
        mock_account = Account(
            account_number="12345678-01",
            cash=10000000.0,
            positions=[
                Position(symbol="005930", quantity=10, avg_price=70000, current_price=75000, exchange="KR"), # Samsung
                Position(symbol="000660", quantity=5, avg_price=110000, current_price=110000, exchange="KR")  # SK Hynix
            ]

        )

        api_client.get_account_balance.return_value = mock_account
        
        # Mock Place Order
        api_client.place_order.return_value = "ORD12345"
        
        # 2. Setup AutoTrader
        # 2. Setup AutoTrader
        trader = AutoTrader(api_client, universe=["005930", "000660", "035420"], market="KR", dry_run=False)

        
        # Mock StockSelector Metrics
        # Create a dummy DataFrame that selector logic would produce
        mock_metrics = pd.DataFrame({
            'ticker': ["005930", "000660", "035420"],
            'score': [1.5, 0.8, 2.0], # 005930: Good, 000660: Bad, 035420: Best
            'current_price': [75000, 110000, 200000],
            'exchange': ['KR', 'KR', 'KR']
        })
        trader.selector.calculate_metrics = MagicMock(return_value=mock_metrics)
        
        # Mock Sentiment Analysis
        # Inject mock model directly to avoid API calls
        mock_llm = MagicMock()
        mock_llm.generate_content.return_value.text = "-0.8" # Negative sentiment for test
        trader.sentiment_analyzer.gemini_model = mock_llm
        
        # 3. Execute Daily Routine
        print("Running run_daily_routine()...")
        trader.run_daily_routine()
        
        # 4. Verify Actions
        
        # Check if balance was queried
        api_client.get_account_balance.assert_called()
        
        # Check if orders were placed
        # We expect:
        # - 000660 (SK Hynix): Score 0.8 (<1.0) -> Sell (MinScoreExit)
        # - 035420 (Naver): Score 2.0 -> Buy (Rebalancing)
        # - 005930 (Samsung): Score 1.5 -> Hold/Buy
        
        print("\nVerifying Order Calls:")
        calls = api_client.place_order.call_args_list
        found_sell = False
        found_buy = False
        
        for call in calls:
            order = call[0][0] # First arg is Order object
            print(f"- Order: {order.side} {order.symbol} {order.quantity} @ {order.price}")
            
            if order.symbol == "000660" and order.side.name == "SELL":
                found_sell = True
            if order.symbol == "035420" and order.side.name == "BUY":
                found_buy = True
                
        self.assertTrue(found_sell, "Failed to sell low score stock (000660)")
        self.assertTrue(found_buy, "Failed to buy high score stock (035420)")
        
        print("\n--- Pipeline Test Completed Successfully ---")

if __name__ == '__main__':
    unittest.main()
