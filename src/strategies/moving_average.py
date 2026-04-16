"""이중 이동평균 교차 전략 (Dual Moving Average Crossover)

단기 이동평균선이 장기 이동평균선을 상향 돌파하면 매수,
하향 돌파하면 매도하는 전략입니다.
"""

import pandas as pd
import numpy as np
from src.strategies.base import BaseStrategy


class DualMAStrategy(BaseStrategy):
    """이중 이동평균 교차 전략
    
    골든크로스(단기MA > 장기MA) → 매수
    데드크로스(단기MA < 장기MA) → 매도
    """
    
    def __init__(self, short_window: int = 5, long_window: int = 20):
        """초기화
        
        Args:
            short_window: 단기 이동평균 기간
            long_window: 장기 이동평균 기간
        """
        super().__init__(name="Dual MA Crossover")
        
        if short_window >= long_window:
            raise ValueError("단기 윈도우는 장기 윈도우보다 작아야 합니다")
        
        self.short_window = short_window
        self.long_window = long_window
        
        self.parameters = {
            'short_window': short_window,
            'long_window': long_window
        }
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """매매 신호 생성
        
        Args:
            data: 주가 데이터
            
        Returns:
            신호 데이터프레임
        """
        self.validate_data(data)
        
        signals = data.copy()
        
        # 이동평균 계산
        signals['short_ma'] = signals['close'].rolling(
            window=self.short_window,
            min_periods=1
        ).mean()
        
        signals['long_ma'] = signals['close'].rolling(
            window=self.long_window,
            min_periods=1
        ).mean()
        
        # 초기화
        signals['signal'] = 0
        signals['position'] = 0
        
        # 골든크로스/데드크로스 감지
        # 단기MA가 장기MA를 상향 돌파 → 매수 (1)
        # 단기MA가 장기MA를 하향 돌파 → 매도 (-1)
        
        for i in range(1, len(signals)):
            prev_short = signals['short_ma'].iloc[i-1]
            prev_long = signals['long_ma'].iloc[i-1]
            curr_short = signals['short_ma'].iloc[i]
            curr_long = signals['long_ma'].iloc[i]
            
            # 골든크로스: 이전에는 단기 < 장기, 현재는 단기 > 장기
            if prev_short <= prev_long and curr_short > curr_long:
                signals.loc[signals.index[i], 'signal'] = 1
                signals.loc[signals.index[i], 'position'] = 1
            
            # 데드크로스: 이전에는 단기 > 장기, 현재는 단기 < 장기
            elif prev_short >= prev_long and curr_short < curr_long:
                signals.loc[signals.index[i], 'signal'] = -1
                signals.loc[signals.index[i], 'position'] = 0
            
            # 그 외에는 이전 포지션 유지
            else:
                signals.loc[signals.index[i], 'position'] = signals['position'].iloc[i-1]
        
        return signals[['signal', 'position', 'short_ma', 'long_ma']]
