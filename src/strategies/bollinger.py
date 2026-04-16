"""볼린저밴드 평균회귀 전략 (Bollinger Band Mean Reversion)

볼린저밴드의 상/하단 밴드를 활용하여
과도한 변동 후 평균으로 회귀하는 성향을 포착하는 전략입니다.
"""

import pandas as pd
import numpy as np
from src.strategies.base import BaseStrategy


class BollingerBandStrategy(BaseStrategy):
    """볼린저밴드 평균회귀 전략
    
    가격이 하단 밴드 터치 → 매수 (저점)
    가격이 상단 밴드 또는 중심선 터치 → 매도
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0, band_proximity_pct: float = 0.01):
        """초기화

        Args:
            period: 이동평균 기간
            std_dev: 표준편차 배수
            band_proximity_pct: 하단 밴드 근접 허용 비율 (기본값 1%)
        """
        super().__init__(name="Bollinger Band Mean Reversion")

        self.period = period
        self.std_dev = std_dev
        self.band_proximity_pct = band_proximity_pct

        self.parameters = {
            'period': period,
            'std_dev': std_dev,
            'band_proximity_pct': band_proximity_pct
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
        
        # 볼린저밴드 계산
        signals['bb_middle'] = signals['close'].rolling(
            window=self.period,
            min_periods=1
        ).mean()
        
        rolling_std = signals['close'].rolling(
            window=self.period,
            min_periods=1
        ).std()
        
        signals['bb_upper'] = signals['bb_middle'] + (rolling_std * self.std_dev)
        signals['bb_lower'] = signals['bb_middle'] - (rolling_std * self.std_dev)
        
        # 초기화
        signals['signal'] = 0
        signals['position'] = 0
        
        # 신호 생성
        for i in range(1, len(signals)):
            curr_price = signals['close'].iloc[i]
            curr_lower = signals['bb_lower'].iloc[i]
            curr_upper = signals['bb_upper'].iloc[i]
            curr_middle = signals['bb_middle'].iloc[i]
            prev_position = signals['position'].iloc[i-1]
            
            # 하단 밴드 근처 또는 아래 → 매수
            if curr_price <= curr_lower * (1 + self.band_proximity_pct):  # 여유 비율
                signals.loc[signals.index[i], 'signal'] = 1
                signals.loc[signals.index[i], 'position'] = 1
            
            # 중심선 이상 또는 상단 밴드 근처 → 매도 (포지션 있을 때만)
            elif prev_position > 0 and (curr_price >= curr_middle or curr_price >= curr_upper * 0.99):
                signals.loc[signals.index[i], 'signal'] = -1
                signals.loc[signals.index[i], 'position'] = 0
            
            # 그 외에는 이전 포지션 유지
            else:
                signals.loc[signals.index[i], 'position'] = prev_position
        
        return signals[['signal', 'position', 'bb_upper', 'bb_middle', 'bb_lower']]
