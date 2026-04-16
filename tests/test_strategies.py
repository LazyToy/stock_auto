"""전략 프레임워크 테스트

TDD: 먼저 전략의 동작을 테스트로 정의합니다.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class TestBaseStrategy:
    """기본 전략 인터페이스 테스트"""
    
    def test_base_strategy_interface(self):
        """BaseStrategy가 필수 메서드를 정의하는지 테스트"""
        from src.strategies.base import BaseStrategy
        
        # 추상 클래스는 직접 인스턴스화할 수 없음
        with pytest.raises(TypeError):
            BaseStrategy(name="test")
    
    def test_strategy_requires_generate_signals(self):
        """전략은 generate_signals 메서드를 구현해야 함"""
        from src.strategies.base import BaseStrategy
        
        # generate_signals 없이 상속하면 에러
        class IncompleteStrategy(BaseStrategy):
            pass
        
        with pytest.raises(TypeError):
            IncompleteStrategy(name="incomplete")


class TestDualMAStrategy:
    """이중 이동평균 교차 전략 테스트"""
    
    @pytest.fixture
    def sample_data(self):
        """테스트용 샘플 데이터 생성"""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        
        # 상승 트렌드 시뮬레이션
        prices = 70000 + np.cumsum(np.random.randn(100) * 500 + 100)
        
        df = pd.DataFrame({
            'datetime': dates,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.random.randint(100000, 1000000, 100)
        })
        
        return df
    
    def test_dual_ma_strategy_creation(self):
        """이중 MA 전략 생성 테스트"""
        from src.strategies.moving_average import DualMAStrategy
        
        strategy = DualMAStrategy(short_window=5, long_window=20)
        
        assert strategy.short_window == 5
        assert strategy.long_window == 20
        assert strategy.name == "Dual MA Crossover"
    
    def test_generate_signals(self, sample_data):
        """매매 신호 생성 테스트"""
        from src.strategies.moving_average import DualMAStrategy
        
        strategy = DualMAStrategy(short_window=5, long_window=20)
        signals = strategy.generate_signals(sample_data)
        
        # 신호는 DataFrame이어야 함
        assert isinstance(signals, pd.DataFrame)
        
        # 필수 컬럼 확인
        assert 'signal' in signals.columns
        assert 'position' in signals.columns
        
        # 신호는 -1, 0, 1 중 하나
        assert signals['signal'].isin([-1, 0, 1]).all()
    
    def test_golden_cross_buy_signal(self):
        """골든크로스 시 매수 신호 테스트"""
        from src.strategies.moving_average import DualMAStrategy
        
        # 골든크로스 발생 데이터
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        prices = np.concatenate([
            np.ones(15) * 70000,  # 횡보
            70000 + np.cumsum(np.ones(15) * 1000)  # 급등
        ])
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = DualMAStrategy(short_window=5, long_window=20)
        signals = strategy.generate_signals(df)
        
        # 골든크로스 발생 지점에서 매수 신호
        buy_signals = signals[signals['signal'] == 1]
        assert len(buy_signals) > 0
    
    def test_dead_cross_sell_signal(self):
        """데드크로스 시 매도 신호 테스트"""
        from src.strategies.moving_average import DualMAStrategy
        
        # 데드크로스 발생 데이터
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        prices = np.concatenate([
            np.ones(15) * 75000,  # 횡보
            75000 - np.cumsum(np.ones(15) * 1000)  # 급락
        ])
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = DualMAStrategy(short_window=5, long_window=20)
        signals = strategy.generate_signals(df)
        
        # 데드크로스 발생 지점에서 매도 신호
        sell_signals = signals[signals['signal'] == -1]
        assert len(sell_signals) > 0


class TestRSIStrategy:
    """RSI 모멘텀 전략 테스트"""
    
    def test_rsi_strategy_creation(self):
        """RSI 전략 생성 테스트"""
        from src.strategies.rsi import RSIStrategy
        
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        
        assert strategy.period == 14
        assert strategy.oversold == 30
        assert strategy.overbought == 70
    
    def test_rsi_oversold_buy_signal(self):
        """RSI 과매도 시 매수 신호 테스트"""
        from src.strategies.rsi import RSIStrategy
        
        # RSI가 30 미만으로 떨어지는 데이터
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        prices = 75000 - np.cumsum(np.random.rand(30) * 500 + 100)  # 하락
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        signals = strategy.generate_signals(df)
        
        # 과매도 구간에서 매수 신호
        buy_signals = signals[signals['signal'] == 1]
        assert len(buy_signals) > 0
    
    def test_rsi_overbought_sell_signal(self):
        """RSI 과매수 시 매도 신호 테스트"""
        from src.strategies.rsi import RSIStrategy
        
        # RSI가 70 이상으로 올라가는 데이터
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        prices = 70000 + np.cumsum(np.random.rand(30) * 500 + 100)  # 상승
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        signals = strategy.generate_signals(df)
        
        # 과매수 구간에서 매도 신호
        sell_signals = signals[signals['signal'] == -1]
        assert len(sell_signals) > 0


class TestBollingerBandStrategy:
    """볼린저밴드 평균회귀 전략 테스트"""
    
    def test_bollinger_strategy_creation(self):
        """볼린저밴드 전략 생성 테스트"""
        from src.strategies.bollinger import BollingerBandStrategy
        
        strategy = BollingerBandStrategy(period=20, std_dev=2.0)
        
        assert strategy.period == 20
        assert strategy.std_dev == 2.0
    
    def test_lower_band_buy_signal(self):
        """하단 밴드 터치 시 매수 신호 테스트"""
        from src.strategies.bollinger import BollingerBandStrategy
        
        # 볼린저밴드 하단으로 떨어지는 데이터
        dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
        prices = 75000 + np.random.randn(50) * 1000
        prices[45:] = 70000  # 급락
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = BollingerBandStrategy(period=20, std_dev=2.0)
        signals = strategy.generate_signals(df)
        
        # 하단 밴드 근처에서 매수 신호
        buy_signals = signals[signals['signal'] == 1]
        assert len(buy_signals) > 0


class TestMACDStrategy:
    """MACD 트렌드 추종 전략 테스트"""
    
    def test_macd_strategy_creation(self):
        """MACD 전략 생성 테스트"""
        from src.strategies.macd import MACDStrategy
        
        strategy = MACDStrategy(fast=12, slow=26, signal=9)
        
        assert strategy.fast == 12
        assert strategy.slow == 26
        assert strategy.signal == 9
    
    def test_macd_crossover_buy_signal(self):
        """MACD 상향 교차 시 매수 신호 테스트"""
        from src.strategies.macd import MACDStrategy
        
        # MACD 상향 교차 데이터
        dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
        prices = 70000 + np.cumsum(np.random.randn(50) * 200 + 50)
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = MACDStrategy(fast=12, slow=26, signal=9)
        signals = strategy.generate_signals(df)
        
        # MACD 상향 교차에서 매수 신호
        buy_signals = signals[signals['signal'] == 1]
        assert len(buy_signals) > 0


class TestMultiIndicatorStrategy:
    """복합 지표 전략 테스트"""
    
    def test_multi_indicator_creation(self):
        """복합 지표 전략 생성 테스트"""
        from src.strategies.multi_indicator import MultiIndicatorStrategy
        
        strategy = MultiIndicatorStrategy(
            ma_short=5,
            ma_long=20,
            rsi_period=14,
            bb_period=20,
            macd_fast=12
        )
        
        assert strategy.ma_short == 5
        assert strategy.rsi_period == 14
    
    def test_consensus_signal_generation(self):
        """복수 지표 합의 신호 생성 테스트"""
        from src.strategies.multi_indicator import MultiIndicatorStrategy
        
        # 모든 지표가 동의하는 상승 추세 데이터
        dates = pd.date_range(start='2024-01-01', periods=60, freq='D')
        prices = 70000 + np.cumsum(np.ones(60) * 300)
        
        df = pd.DataFrame({
            'datetime': dates,
            'close': prices,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1000000
        })
        
        strategy = MultiIndicatorStrategy(
            ma_short=5,
            ma_long=20,
            rsi_period=14,
            bb_period=20,
            macd_fast=12,
            min_agreement=3  # 최소 3개 지표 동의
        )
        
        signals = strategy.generate_signals(df)
        
        # 강한 합의 신호 존재
        strong_signals = signals[abs(signals['signal']) > 0]
        assert len(strong_signals) > 0
