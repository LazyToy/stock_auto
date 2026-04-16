"""Exit Strategy Verification Script

Simulates various market conditions to verify:
1. Stop Loss: Price drops 10% below avg price -> SELL
2. Trailing Stop: Price rises 20%, then drops 5% from peak -> SELL
3. Min Score: Score drops below 1.0 -> SELL
"""

import sys
import unittest
from unittest.mock import MagicMock, PropertyMock

# 프로젝트 루트 경로 추가
sys.path.append(r"d:\HY\develop_Project\stock_auto")

from src.trader.auto_trader import AutoTrader
from src.data.models import Account, Position, OrderSide
from src.trader.state_manager import StateManager

class TestExitStrategies(unittest.TestCase):
    def setUp(self):
        self.mock_api = MagicMock()
        self.universe = ["005930.KS", "000660.KS"]
        self.trader = AutoTrader(self.mock_api, self.universe, dry_run=True)
        
        # StateManager Mocking (파일 생성 방지)
        self.trader.state_manager = MagicMock(spec=StateManager)
        self.trader.state_manager.get_high_water_mark.return_value = 0.0
        
    def test_stop_loss(self):
        """1. Stop Loss Test (-10%)"""
        print("\n[Test] Stop Loss Logic")
        
        # 보유 종목: 평단 10,000원, 현재가 8,900원 (-11%)
        position = MagicMock(spec=Position)
        position.symbol = "005930.KS"
        position.quantity = 10
        position.avg_price = 10000
        position.current_price = 8900
        
        account = MagicMock(spec=Account)
        account.positions = [position]
        account.total_value = 1000000
        
        # 현재 점수는 정상 (1.5)이라고 가정
        current_scores = {"005930.KS": 1.5}
        
        sold_tickers = self.trader._process_exit_strategies(account, current_scores)
        
        # 검증: 매도 목록에 포함되어야 함
        self.assertIn("005930.KS", sold_tickers)
        # 주문 실행 확인
        self.mock_api.place_order.assert_not_called() # dry_run이라 호출 안됨, 로그로 확인
        print("-> Stop Loss Triggered correctly.")

    def test_trailing_stop(self):
        """2. Trailing Stop Test (Profit > 10%, Drop -5% from Peak)"""
        print("\n[Test] Trailing Stop Logic")
        
        # 보유 종목: 평단 10,000원
        # 시나리오: 12,000원(고점) 갔다가 11,300원으로 하락
        # 수익률: +13% (10% 초과 OK)
        # 고점 대비 하락: (11300 - 12000) / 12000 = -5.8% (5% 하락 OK) -> 매도해야 함
        
        position = MagicMock(spec=Position)
        position.symbol = "000660.KS"
        position.quantity = 10
        position.avg_price = 10000
        position.current_price = 11300
        
        account = MagicMock(spec=Account)
        account.positions = [position]
        
        # Mock StateManager behavior
        self.trader.state_manager.get_high_water_mark.return_value = 12000 # 이미 고점은 12000으로 기록됨
        
        current_scores = {"000660.KS": 1.5}
        
        sold_tickers = self.trader._process_exit_strategies(account, current_scores)
        
        self.assertIn("000660.KS", sold_tickers)
        print("-> Trailing Stop Triggered correctly.")

    def test_min_score(self):
        """3. Minimum Score Test (Score < 1.0)"""
        print("\n[Test] Min Score Logic")
        
        # 보유 종목: 가격은 평단 근처 (손절/익절 아님)
        position = MagicMock(spec=Position)
        position.symbol = "035420.KS"
        position.quantity = 10
        position.avg_price = 10000
        position.current_price = 10000
        
        account = MagicMock(spec=Account)
        account.positions = [position]
        
        # Mock Scores: 점수가 0.8로 떨어짐
        current_scores = {"035420.KS": 0.8}
        
        sold_tickers = self.trader._process_exit_strategies(account, current_scores)
        
        self.assertIn("035420.KS", sold_tickers)
        print("-> Min Score Exit Triggered correctly.")

if __name__ == '__main__':
    unittest.main()
