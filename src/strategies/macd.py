"""MACD 트렌드 추종 전략 (MACD Trend Following)

MACD 지표를 사용하여 트렌드의 방향과 모멘텀을 파악하고
트렌드를 추종하는 전략입니다.
"""

import pandas as pd
import numpy as np
from src.strategies.base import BaseStrategy


class MACDStrategy(BaseStrategy):
    """MACD 트렌드 추종 전략
    
    MACD선이 Signal선을 상향 돌파 → 매수
    MACD선이 Signal선을 하향 돌파 → 매도
    """
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """초기화
        
        Args:
            fast: 빠른 EMA 기간
            slow: 느린 EMA 기간
            signal: Signal 선 EMA 기간
        """
        super().__init__(name="MACD Trend Following")
        
        self.fast = fast
        self.slow = slow
        self.signal = signal
        
        self.parameters = {
            'fast': fast,
            'slow': slow,
            'signal': signal
        }
    
    def calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """EMA 계산
        
        Args:
            prices: 가격 시리즈
            period: EMA 기간
            
        Returns:
            EMA 시리즈
        """
        return prices.ewm(span=period, adjust=False).mean()
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """매매 신호 생성
        
        Args:
            data: 주가 데이터
            
        Returns:
            신호 데이터프레임
        """
        self.validate_data(data)
        
        signals = data.copy()
        
        # MACD 계산
        ema_fast = self.calculate_ema(signals['close'], self.fast)
        ema_slow = self.calculate_ema(signals['close'], self.slow)
        
        signals['macd'] = ema_fast - ema_slow
        signals['signal_line'] = self.calculate_ema(signals['macd'], self.signal)
        signals['histogram'] = signals['macd'] - signals['signal_line']
        
        # 초기화
        signals['signal'] = 0
        signals['position'] = 0
        
        # 신호 생성
        for i in range(1, len(signals)):
            prev_macd = signals['macd'].iloc[i-1]
            prev_signal_line = signals['signal_line'].iloc[i-1]
            curr_macd = signals['macd'].iloc[i]
            curr_signal_line = signals['signal_line'].iloc[i]
            
            # MACD 상향 교차 → 매수
            if prev_macd <= prev_signal_line and curr_macd > curr_signal_line:
                signals.loc[signals.index[i], 'signal'] = 1
                signals.loc[signals.index[i], 'position'] = 1
            
            # MACD 하향 교차 → 매도
            elif prev_macd >= prev_signal_line and curr_macd < curr_signal_line:
                signals.loc[signals.index[i], 'signal'] = -1
                signals.loc[signals.index[i], 'position'] = 0
            
            # 그 외에는 이전 포지션 유지
            else:
                signals.loc[signals.index[i], 'position'] = signals['position'].iloc[i-1]
        
        return signals[['signal', 'position', 'macd', 'signal_line', 'histogram']]
