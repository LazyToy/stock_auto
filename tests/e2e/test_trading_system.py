
import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.analysis.regime import RegimeDetector, MarketRegime
from src.strategies.adaptive_strategy import AdaptiveStrategy
from src.strategies.ml_strategy import RandomForestStrategy
from src.broker.base import BaseBroker
from src.data.models import Order, OrderSide, OrderType, Account, StockPrice, Position

class TestTradingSystem(unittest.TestCase):
    def setUp(self):
        # 1. Setup Data (simulate Bull market)
        # Create a DataFrame with increasing prices (Bull)
        prices = list(range(100, 150))
        dates = pd.date_range(start='2024-01-01', periods=len(prices))
        self.market_data = pd.DataFrame({
            'open': prices, 'high': [p+1 for p in prices], 
            'low': [p-1 for p in prices], 'close': prices, 
            'volume': [1000]*len(prices)
        }, index=dates)
        
        # 2. Setup Strategies
        # Regime Detector (Real or Mock)
        # Here we use Real Logic but since data is simple, real detector might be tricky with small data.
        # So let's mock detector for stability in unit test, 
        # BUT this is E2E test, so we should try integration if possible.
        # Let's use Mock for detector to control regime explicitly.
        self.detector = MagicMock(spec=RegimeDetector)
        self.detector.detect.return_value = MarketRegime.BULL
        
        # Strategies
        self.bull_strategy = RandomForestStrategy(n_estimators=10) # Small for speed
        # Mock its train method to avoid long training and sklearn dependency issues in test
        self.bull_strategy.train = MagicMock(return_value=1.0)
        self.bull_strategy.predict = MagicMock(return_value=MagicMock(signal=1, probability=0.9))
        self.bull_strategy.is_trained = True
        
        self.strategy_map = {
            MarketRegime.BULL: self.bull_strategy,
            MarketRegime.BEAR: MagicMock(), # Not used
            MarketRegime.SIDEWAYS: MagicMock() # Not used
        }
        
        self.adaptive_strategy = AdaptiveStrategy(self.detector, self.strategy_map)
        
        # 3. Setup Broker (Mock)
        self.broker = MagicMock(spec=BaseBroker)
        self.broker.get_current_price.return_value = 150.0
        self.broker.place_order.return_value = "ORD12345"
        self.broker.get_account_balance.return_value = Account(
            account_number="12345678",
            cash=1000000, 
            positions=[]
        )
        
    def test_bull_market_buy_execution(self):
        """상승장에서 매수 신호 발생 및 주문 실행 시나리오"""
        
        # 1. Strategy Signal Generation
        signal_df = self.adaptive_strategy.generate_signals(self.market_data)
        
        # Verify Signal
        # AdaptiveStrategy delegates to bull_strategy (RandomForest) which is mocked to return signal=1
        # However, generate_signals returns a DataFrame with 'signal' column.
        # RandomForestStrategy.generate_signals sets the last row's signal.
        
        # Wait, I mocked `predict` but `generate_signals` uses `predict`.
        # So `MLStrategy.generate_signals` will call `predict` and set dataframe signal.
        # But `AdaptiveStrategy.generate_signals` calls `strategy.generate_signals`.
        # So we need to ensure `bull_strategy.generate_signals` works or is mocked.
        # Since `bull_strategy` is a real instance with mocked methods, `generate_signals` (inherited from MLStrategy) will run.
        
        # MLStrategy.generate_signals:
        # if not self.is_trained: ... (We set is_trained=True)
        # prediction = self.predict(df) (We mocked predict)
        # df['signal'] = 0 ... df.iloc[-1] = prediction.signal
        
        self.assertEqual(signal_df['signal'].iloc[-1], 1)
        
        # 2. Execution Logic (Simulation)
        # Assuming we have a Trader class that takes strategy and broker. 
        # But since we didn't refactor AutoTrader yet, let's simulate the logic here:
        
        current_signal = signal_df['signal'].iloc[-1]
        symbol = "005930"
        
        if current_signal == 1:
            current_price = self.broker.get_current_price(symbol)
            quantity = 10 # Hardcoded for test
            
            order = Order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                price=current_price,
                quantity=quantity,
                created_at=self.market_data.index[-1]
            )
            
            order_id = self.broker.place_order(order)
            
            # 3. Verify Broker Interaction
            self.broker.get_current_price.assert_called_with(symbol)
            self.broker.place_order.assert_called_once()
            self.assertEqual(order_id, "ORD12345")
            
            # Check Order Details
            args = self.broker.place_order.call_args[0][0]
            self.assertEqual(args.symbol, symbol)
            self.assertEqual(args.side, OrderSide.BUY)
            self.assertEqual(args.quantity, quantity)
            
if __name__ == '__main__':
    unittest.main()
