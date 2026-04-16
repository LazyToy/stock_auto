import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.analysis.regime import RegimeDetector, MarketRegime
from src.strategies.adaptive_strategy import AdaptiveStrategy
from src.strategies.base import BaseStrategy

class TestAdaptiveStrategy(unittest.TestCase):
    def setUp(self):
        # Mock Strategies
        self.bull_strategy = MagicMock()
        # Mocking DataFrame return
        self.bull_strategy.generate_signals.return_value = pd.DataFrame({"signal": [1], "confidence": [0.9]})
        
        self.bear_strategy = MagicMock()
        self.bear_strategy.generate_signals.return_value = pd.DataFrame({"signal": [-1], "confidence": [0.8]})
        
        self.sideways_strategy = MagicMock()
        self.sideways_strategy.generate_signals.return_value = pd.DataFrame({"signal": [0], "confidence": [0.5]})
        
        self.strategy_map = {
            MarketRegime.BULL: self.bull_strategy,
            MarketRegime.BEAR: self.bear_strategy,
            MarketRegime.SIDEWAYS: self.sideways_strategy
        }
        
        self.detector = MagicMock(spec=RegimeDetector)
        self.adaptive_strategy = AdaptiveStrategy(self.detector, self.strategy_map)

    def test_bull_market_regime(self):
        """상승장 레짐 감지 시 상승장 전략 선택 확인"""
        market_data = pd.DataFrame({'close': [100, 110, 120]})
        self.detector.detect.return_value = MarketRegime.BULL
        
        signal = self.adaptive_strategy.generate_signals(market_data)
        
        self.detector.detect.assert_called_with(market_data)
        self.bull_strategy.generate_signals.assert_called_with(market_data)
        self.bear_strategy.generate_signals.assert_not_called()
        self.assertEqual(signal['signal'].iloc[0], 1)

    def test_bear_market_regime(self):
        """하락장 레짐 감지 시 하락장 전략 선택 확인"""
        market_data = pd.DataFrame({'close': [120, 110, 100]})
        self.detector.detect.return_value = MarketRegime.BEAR
        
        signal = self.adaptive_strategy.generate_signals(market_data)
        
        self.bear_strategy.generate_signals.assert_called_with(market_data)
        self.assertEqual(signal['signal'].iloc[0], -1)

    def test_default_strategy(self):
        """매핑되지 않은 레짐일 경우 빈 데이터프레임 반환 확인"""
        import pandas as pd
        market_data = pd.DataFrame({'close': [100, 100, 100]})
        self.detector.detect.return_value = MarketRegime.UNKNOWN
        
        signal = self.adaptive_strategy.generate_signals(market_data)
        
        self.assertTrue(signal.empty)

class TestRegimeDetector(unittest.TestCase):
    def setUp(self):
        # ma_short=5, ma_long=10 으로 설정하여 테스트 데이터 크기 최소화
        self.detector = RegimeDetector(ma_short=5, ma_long=10, atr_period=5)
        
    def test_detect_bull_market(self):
        """상승장 감지 테스트 (단기 > 장기)"""
        # 1. Generate data where MA5 > MA10
        # Increasing sequence ensures MA5 > MA10 eventually
        prices = list(range(100, 130)) 
        dates = pd.date_range(start='2024-01-01', periods=len(prices))
        
        df = pd.DataFrame({
            'open': prices, 'high': prices, 'low': prices, 'close': prices, 'volume': 1000
        }, index=dates)
        
        # Add shift to low close for ATR calculation prevention of NaN if needed, 
        # but pure increasing close implies high=low=close roughly for simple test.
        # Actually RegimeDetector needs high/low for ATR. 
        # Provided simple data.
        
        regime = self.detector.detect(df)
        self.assertEqual(regime, MarketRegime.BULL)

    def test_detect_bear_market(self):
        """하락장 감지 테스트 (단기 < 장기)"""
        prices = list(range(130, 100, -1))
        dates = pd.date_range(start='2024-01-01', periods=len(prices))
        df = pd.DataFrame({
            'open': prices, 'high': prices, 'low': prices, 'close': prices, 'volume': 1000
        }, index=dates)
        
        regime = self.detector.detect(df)
        self.assertEqual(regime, MarketRegime.BEAR)

if __name__ == '__main__':
    unittest.main()
