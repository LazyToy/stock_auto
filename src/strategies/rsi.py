"""RSI 모멘텀 전략 (RSI Momentum Strategy)

RSI 지표를 사용하여 과매수/과매도 구간을 파악하고
역추세 매매를 수행하는 전략입니다.
"""

import pandas as pd
import numpy as np
from src.strategies.base import BaseStrategy


class RSIStrategy(BaseStrategy):
    """RSI 모멘텀 전략
    
    RSI < oversold → 과매도 → 매수
    RSI > overbought → 과매수 → 매도
    """
    
    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70):
        """초기화
        
        Args:
            period: RSI 계산 기간
            oversold: 과매도 기준선
            overbought: 과매수 기준선
        """
        super().__init__(name="RSI Momentum")
        
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        
        self.parameters = {
            'period': period,
            'oversold': oversold,
            'overbought': overbought
        }
    
    def calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """RSI 계산
        
        Args:
            prices: 가격 시리즈
            
        Returns:
            RSI 시리즈
        """
        # 가격 변화
        delta = prices.diff()
        
        # 상승분과 하락분 분리
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # 평균 계산 (Wilder's smoothing — EMA with com = period - 1)
        avg_gain = gain.ewm(com=self.period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=self.period - 1, adjust=False).mean()
        
        # RS = Average Gain / Average Loss
        rs = avg_gain / avg_loss
        
        # RSI = 100 - (100 / (1 + RS))
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """매매 신호 생성
        
        Args:
            data: 주가 데이터
            
        Returns:
            신호 데이터프레임
        """
        self.validate_data(data)
        
        signals = data.copy()
        
        # RSI 계산
        signals['rsi'] = self.calculate_rsi(signals['close'])
        
        # 초기화
        signals['signal'] = 0
        signals['position'] = 0
        
        # 신호 생성
        for i in range(1, len(signals)):
            curr_rsi = signals['rsi'].iloc[i]
            prev_rsi = signals['rsi'].iloc[i-1]
            
            # 과매도 구간 또는 과매도 탈출 → 매수
            if curr_rsi <= self.oversold or (prev_rsi <= self.oversold and curr_rsi > self.oversold):
                signals.loc[signals.index[i], 'signal'] = 1
                signals.loc[signals.index[i], 'position'] = 1
            
            # 과매수 구간 또는 과매수 이탈 → 매도
            elif curr_rsi >= self.overbought or (prev_rsi >= self.overbought and curr_rsi < self.overbought):
                signals.loc[signals.index[i], 'signal'] = -1
                signals.loc[signals.index[i], 'position'] = 0
            
            # 그 외에는 이전 포지션 유지
            else:
                signals.loc[signals.index[i], 'position'] = signals['position'].iloc[i-1]
        
        return signals[['signal', 'position', 'rsi']]
