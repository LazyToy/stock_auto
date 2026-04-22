"""복합 지표 전략 (Multi-Indicator Composite Strategy)

여러 기술적 지표를 조합하여 신호의 정확도를 높이는 전략입니다.
MA, RSI, MACD, Bollinger Bands를 모두 활용합니다.
"""

import pandas as pd
import numpy as np
from src.strategies.base import BaseStrategy
from src.strategies.moving_average import DualMAStrategy
from src.strategies.rsi import RSIStrategy
from src.strategies.bollinger import BollingerBandStrategy
from src.strategies.macd import MACDStrategy


class MultiIndicatorStrategy(BaseStrategy):
    """복합 지표 전략
    
    여러 지표의 합의(consensus)를 통해 신호 생성
    최소 min_agreement개 이상의 지표가 동의해야 매매 신호 발생
    """
    
    def __init__(
        self,
        ma_short: int = 5,
        ma_long: int = 20,
        rsi_period: int = 14,
        bb_period: int = 20,
        macd_fast: int = 12,
        min_agreement: int = 3
    ):
        """초기화
        
        Args:
            ma_short: 단기 이동평균 기간
            ma_long: 장기 이동평균 기간
            rsi_period: RSI 기간
            bb_period: 볼린저밴드 기간
            macd_fast: MACD 빠른 EMA 기간
            min_agreement: 최소 합의 지표 수
        """
        super().__init__(name="Multi-Indicator Composite")
        
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.macd_fast = macd_fast
        self.min_agreement = min_agreement
        
        # 개별 전략 생성
        self.ma_strategy = DualMAStrategy(short_window=ma_short, long_window=ma_long)
        self.rsi_strategy = RSIStrategy(period=rsi_period)
        self.bb_strategy = BollingerBandStrategy(period=bb_period)
        self.macd_strategy = MACDStrategy(fast=macd_fast)
        
        self.parameters = {
            'ma_short': ma_short,
            'ma_long': ma_long,
            'rsi_period': rsi_period,
            'bb_period': bb_period,
            'macd_fast': macd_fast,
            'min_agreement': min_agreement
        }
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """매매 신호 생성
        
        Args:
            data: 주가 데이터
            
        Returns:
            신호 데이터프레임
        """
        self.validate_data(data)
        
        # 각 전략의 신호 수집
        ma_signals = self.ma_strategy.generate_signals(data)
        rsi_signals = self.rsi_strategy.generate_signals(data)
        bb_signals = self.bb_strategy.generate_signals(data)
        macd_signals = self.macd_strategy.generate_signals(data)
        
        # 결과 데이터프레임 초기화
        signals = data.copy()
        signals['ma_signal'] = ma_signals['signal']
        signals['rsi_signal'] = rsi_signals['signal']
        signals['bb_signal'] = bb_signals['signal']
        signals['macd_signal'] = macd_signals['signal']
        
        # 합의 신호 계산
        signals['signal'] = 0
        signals['position'] = 0
        signals['agreement_score'] = 0
        
        for i in range(len(signals)):
            # 각 지표의 신호 수집
            ma_sig = signals['ma_signal'].iloc[i]
            rsi_sig = signals['rsi_signal'].iloc[i]
            bb_sig = signals['bb_signal'].iloc[i]
            macd_sig = signals['macd_signal'].iloc[i]

            if ma_sig == 0 and 'position' in ma_signals:
                ma_sig = ma_signals['position'].iloc[i]
            if macd_sig == 0 and 'position' in macd_signals:
                macd_sig = macd_signals['position'].iloc[i]
            if 'rsi' in rsi_signals:
                rsi_value = rsi_signals['rsi'].iloc[i]
                if pd.notna(rsi_value):
                    rsi_sig = 1 if rsi_value >= 50 else -1
            if bb_sig == 0 and {'bb_middle'}.issubset(bb_signals.columns):
                curr_price = signals['close'].iloc[i]
                bb_middle = bb_signals['bb_middle'].iloc[i]
                if pd.notna(bb_middle):
                    bb_sig = 1 if curr_price >= bb_middle else -1
            
            # 매수 신호 카운트
            buy_votes = sum([
                ma_sig == 1,
                rsi_sig == 1,
                bb_sig == 1,
                macd_sig == 1
            ])
            
            # 매도 신호 카운트
            sell_votes = sum([
                ma_sig == -1,
                rsi_sig == -1,
                bb_sig == -1,
                macd_sig == -1
            ])
            
            # 합의 점수 저장
            signals.loc[signals.index[i], 'agreement_score'] = max(buy_votes, sell_votes)
            
            # 최소 합의 수 이상이면 신호 발생
            if buy_votes >= self.min_agreement:
                signals.loc[signals.index[i], 'signal'] = 1
                signals.loc[signals.index[i], 'position'] = 1
            elif sell_votes >= self.min_agreement:
                signals.loc[signals.index[i], 'signal'] = -1
                signals.loc[signals.index[i], 'position'] = 0
            elif i > 0:
                # 합의되지 않으면 이전 포지션 유지
                signals.loc[signals.index[i], 'position'] = signals['position'].iloc[i-1]
        
        return signals[[
            'signal', 'position', 'agreement_score',
            'ma_signal', 'rsi_signal', 'bb_signal', 'macd_signal'
        ]]
