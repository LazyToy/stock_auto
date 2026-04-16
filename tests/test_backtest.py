"""백테스팅 엔진 테스트

TDD: 포트폴리오 관리와 백테스킹 실행 로직을 테스트합니다.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from src.data.models import Order, OrderType, OrderSide, Position


class TestPortfolio:
    """백테스팅 포트폴리오 테스트"""
    
    def test_portfolio_initialization(self):
        """포트폴리오 초기화 테스트"""
        from src.backtest.engine import Portfolio
        
        portfolio = Portfolio(initial_capital=10000000)
        
        assert portfolio.cash == 10000000
        assert portfolio.initial_capital == 10000000
        assert len(portfolio.positions) == 0
        assert len(portfolio.history) == 0
    
    def test_update_position_buy(self):
        """매수 주문 시 포지션 업데이트 테스트"""
        from src.backtest.engine import Portfolio
        
        portfolio = Portfolio(initial_capital=10000000)
        
        # 삼성전자 10주 70,000원에 매수
        portfolio.update_position(
            symbol="005930",
            quantity=10,
            price=70000,
            side=OrderSide.BUY,
            timestamp=datetime.now()
        )
        
        # 수수료 0.015% 계산: 700000 * 0.00015 = 105
        expected_cash = 10000000 - 700000 - 105
        assert portfolio.cash == expected_cash
        assert "005930" in portfolio.positions
        assert portfolio.positions["005930"].quantity == 10
        assert portfolio.positions["005930"].avg_price == 70000
    
    def test_update_position_sell(self):
        """매도 주문 시 포지션 업데이트 테스트"""
        from src.backtest.engine import Portfolio
        
        portfolio = Portfolio(initial_capital=10000000)
        
        # 먼저 매수
        portfolio.update_position(
            symbol="005930",
            quantity=10,
            price=70000,
            side=OrderSide.BUY,
            timestamp=datetime.now()
        )
        
        # 5주 80,000원에 매도
        portfolio.update_position(
            symbol="005930",
            quantity=5,
            price=80000,
            side=OrderSide.SELL,
            timestamp=datetime.now()
        )
        
        # 매수 수수료: 105
        # 매도 수수료: 400000 * 0.00015 = 60
        # 총 현금: 10000000 - 700105 + (400000 - 60)
        expected_cash = 10000000 - 700105 + 399940
        assert portfolio.cash == expected_cash
        assert portfolio.positions["005930"].quantity == 5
    
    def test_insufficient_funds(self):
        """현금 부족 시 처리 테스트"""
        from src.backtest.engine import Portfolio
        
        portfolio = Portfolio(initial_capital=100000)  # 10만원
        
        # 100만원 어치 매수 시도 -> 에러 발생 또는 무시
        # 여기서는 ValueError 발생을 기대
        with pytest.raises(ValueError):
            portfolio.update_position(
                symbol="005930",
                quantity=10,
                price=100000,  # 10주 * 10만원 = 100만원
                side=OrderSide.BUY,
                timestamp=datetime.now()
            )


class TestBacktestEngine:
    """백테스팅 엔진 테스트"""
    
    @pytest.fixture
    def mock_strategy(self):
        """Mock 전략"""
        from src.strategies.base import BaseStrategy
        
        class MockStrategy(BaseStrategy):
            def generate_signals(self, data):
                signals = data.copy()
                signals['signal'] = 0
                signals['position'] = 0
                
                # 첫날 매수
                signals.iloc[0, signals.columns.get_loc('signal')] = 1
                
                # 마지막날 매도
                signals.iloc[-1, signals.columns.get_loc('signal')] = -1
                
                return signals
                
        return MockStrategy(name="Mock")

    @pytest.fixture
    def sample_data(self):
        """테스트 데이터"""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        prices = [10000, 10100, 10200, 10300, 10400, 10500, 10600, 10700, 10800, 10900]
        
        return pd.DataFrame({
            'datetime': dates,
            'open': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'close': prices,
            'volume': 1000
        })

    def test_backtest_run(self, mock_strategy, sample_data):
        """백테스트 실행 테스트"""
        from src.backtest.engine import BacktestEngine
        
        engine = BacktestEngine(
            strategy=mock_strategy,
            symbol="005930",
            data=sample_data,
            initial_capital=1000000
        )
        
        result = engine.run()
        
        # 결과 검증
        assert result.total_return is not None
        assert result.portfolio.cash > 0
        assert len(result.trades) > 0
