"""Exit 전략 구현 모듈

재사용 가능한 청산 전략들을 구현합니다:
- FixedStopLoss: 고정 손절선
- ATRTrailingStop: ATR 기반 동적 Trailing Stop
- PercentTrailingStop: 퍼센트 기반 Trailing Stop  
- PartialTakeProfit: 분할 이익 실현
- TimeBasedExit: 시간 기반 청산
"""

import pandas as pd
from typing import Dict, Set, Optional
from src.strategies.exit_base import BaseExitStrategy, ExitSignal, PositionContext


class FixedStopLoss(BaseExitStrategy):
    """고정 손절 전략
    
    진입가 대비 일정 퍼센트 이상 하락 시 전량 청산합니다.
    """
    
    def __init__(self, stop_pct: float = -0.07):
        """초기화
        
        Args:
            stop_pct: 손절선 (음수, 기본값 -7%)
        """
        super().__init__(name="Fixed Stop Loss")
        self.stop_pct = stop_pct
        self.parameters = {'stop_pct': stop_pct}
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """손절 조건 체크"""
        if context.loss_pct <= self.stop_pct:
            return ExitSignal.full_exit(
                reason=f"STOP_LOSS ({context.loss_pct*100:.1f}% <= {self.stop_pct*100:.1f}%)",
                price=context.current_price
            )
        return ExitSignal.hold()


class ATRTrailingStop(BaseExitStrategy):
    """ATR 기반 Trailing Stop 전략
    
    변동성(ATR)에 비례하여 동적으로 조정되는 Trailing Stop입니다.
    High Water Mark 대비 ATR * Multiplier 만큼 하락 시 청산합니다.
    """
    
    def __init__(self, multiplier: float = 2.0, atr_period: int = 14):
        """초기화
        
        Args:
            multiplier: ATR 배수 (기본값 2.0)
            atr_period: ATR 계산 기간 (기본값 14)
        """
        super().__init__(name="ATR Trailing Stop")
        self.multiplier = multiplier
        self.atr_period = atr_period
        self._high_water_mark: Dict[str, float] = {}
        self.parameters = {
            'multiplier': multiplier,
            'atr_period': atr_period
        }
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """ATR 기반 Trailing Stop 체크"""
        symbol = context.symbol
        
        # High Water Mark 업데이트
        current_hwm = self._high_water_mark.get(symbol, context.avg_price)
        if context.current_price > current_hwm:
            current_hwm = context.current_price
            self._high_water_mark[symbol] = current_hwm
        
        # ATR 값 사용 (context에서 제공되거나 기본값 사용)
        atr = context.atr if context.atr > 0 else context.avg_price * 0.02  # 기본값: 평균가의 2%
        
        # Trailing Stop 가격 계산
        trailing_stop_price = current_hwm - (atr * self.multiplier)
        
        if context.current_price <= trailing_stop_price:
            drop_pct = (context.current_price - current_hwm) / current_hwm * 100
            return ExitSignal.full_exit(
                reason=f"ATR_TRAILING_STOP (고점 {current_hwm:,.0f} 대비 {drop_pct:.1f}% 하락)",
                price=context.current_price
            )
        return ExitSignal.hold()
    
    def reset(self) -> None:
        """상태 초기화"""
        self._high_water_mark.clear()
    
    def update(self, context: PositionContext, market_data: 'pd.Series') -> None:
        """High Water Mark 업데이트"""
        symbol = context.symbol
        current_hwm = self._high_water_mark.get(symbol, context.avg_price)
        if context.current_price > current_hwm:
            self._high_water_mark[symbol] = context.current_price


class PercentTrailingStop(BaseExitStrategy):
    """퍼센트 기반 Trailing Stop 전략
    
    고점 대비 일정 퍼센트 하락 시 청산합니다.
    수익이 일정 수준 이상일 때만 활성화됩니다.
    """
    
    def __init__(self, trail_pct: float = -0.05, activation_pct: float = 0.10):
        """초기화
        
        Args:
            trail_pct: 고점 대비 하락률 (음수, 기본값 -5%)
            activation_pct: 활성화 수익률 (기본값 +10%)
        """
        super().__init__(name="Percent Trailing Stop")
        self.trail_pct = trail_pct
        self.activation_pct = activation_pct
        self._high_water_mark: Dict[str, float] = {}
        self.parameters = {
            'trail_pct': trail_pct,
            'activation_pct': activation_pct
        }
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """Trailing Stop 체크"""
        # 활성화 조건 체크
        if context.profit_pct < self.activation_pct:
            return ExitSignal.hold()
        
        symbol = context.symbol
        
        # High Water Mark 업데이트
        current_hwm = self._high_water_mark.get(symbol, context.current_price)
        if context.current_price > current_hwm:
            current_hwm = context.current_price
            self._high_water_mark[symbol] = current_hwm
        
        # 고점 대비 하락률 계산
        drop_from_hwm = (context.current_price - current_hwm) / current_hwm
        
        if drop_from_hwm <= self.trail_pct:
            return ExitSignal.full_exit(
                reason=f"PERCENT_TRAILING_STOP (수익 {context.profit_pct*100:.1f}%, 고점 대비 {drop_from_hwm*100:.1f}%)",
                price=context.current_price
            )
        return ExitSignal.hold()
    
    def reset(self) -> None:
        """상태 초기화"""
        self._high_water_mark.clear()


class PartialTakeProfit(BaseExitStrategy):
    """분할 이익 실현 전략
    
    수익률 단계별로 부분 청산을 실행합니다.
    """
    
    def __init__(self, levels: Dict[float, float] = None):
        """초기화
        
        Args:
            levels: {수익률: 청산비율} 딕셔너리
                    기본값: {0.10: 0.25, 0.20: 0.50, 0.30: 1.0}
                    → +10%에서 25%, +20%에서 50%, +30%에서 100% 청산
        """
        super().__init__(name="Partial Take Profit")
        self.levels = levels or {0.10: 0.25, 0.20: 0.50, 0.30: 1.0}
        self._realized_levels: Dict[str, Set[float]] = {}
        self.parameters = {'levels': self.levels}
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """이익 실현 조건 체크"""
        symbol = context.symbol
        
        if symbol not in self._realized_levels:
            self._realized_levels[symbol] = set()
        
        realized = self._realized_levels[symbol]
        
        # 수익률 단계별 체크 (낮은 수익률부터)
        for level, ratio in sorted(self.levels.items()):
            if context.profit_pct >= level and level not in realized:
                # 이 레벨 실현 기록
                realized.add(level)
                
                # 이전 레벨에서 이미 청산한 비율 계산
                prev_sold = sum(
                    self.levels[l] for l in realized if l < level
                )
                
                # 남은 포지션 중에서의 청산 비율 계산
                remaining = 1.0 - prev_sold
                actual_ratio = min(ratio, remaining)
                
                if actual_ratio > 0:
                    return ExitSignal.partial_exit(
                        ratio=actual_ratio,
                        reason=f"TAKE_PROFIT_L{int(level*100)} (+{level*100:.0f}% → {ratio*100:.0f}% 청산)",
                        price=context.current_price
                    )
        
        return ExitSignal.hold()
    
    def reset(self) -> None:
        """상태 초기화"""
        self._realized_levels.clear()


class TimeBasedExit(BaseExitStrategy):
    """시간 기반 청산 전략
    
    보유 기간이 일정 일수를 초과하면 청산합니다.
    """
    
    def __init__(self, max_holding_days: int = 30, force_exit: bool = False):
        """초기화
        
        Args:
            max_holding_days: 최대 보유 일수 (기본값 30일)
            force_exit: True면 강제 청산, False면 경고만
        """
        super().__init__(name="Time Based Exit")
        self.max_holding_days = max_holding_days
        self.force_exit = force_exit
        self.parameters = {
            'max_holding_days': max_holding_days,
            'force_exit': force_exit
        }
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """보유 기간 체크"""
        if context.holding_days > self.max_holding_days:
            if self.force_exit:
                return ExitSignal.full_exit(
                    reason=f"TIME_EXIT (보유 {context.holding_days}일 > {self.max_holding_days}일)",
                    price=context.current_price
                )
            # 강제 청산이 아니면 경고만 (다른 전략에서 처리)
        return ExitSignal.hold()


class MinScoreExit(BaseExitStrategy):
    """최소 점수 기반 청산 전략
    
    종목 점수가 일정 수준 미만이면 청산합니다.
    """
    
    def __init__(self, min_score: float = 1.0):
        """초기화
        
        Args:
            min_score: 최소 점수 기준 (기본값 1.0)
        """
        super().__init__(name="Min Score Exit")
        self.min_score = min_score
        self._current_scores: Dict[str, float] = {}
        self.parameters = {'min_score': min_score}
    
    def set_scores(self, scores: Dict[str, float]) -> None:
        """현재 점수 설정"""
        self._current_scores = scores
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """점수 체크"""
        # 우선순위: 1. Context 점수, 2. 내부 저장 점수
        score = context.current_score

        if score < self.min_score:
            return ExitSignal(should_exit=True, reason=f"Score {score} < min {self.min_score}")

        # Context 점수가 기본값(5.0)이고 내부 점수가 있으면 사용
        if score == 5.0 and self._current_scores:
            score = self._current_scores.get(context.symbol, 5.0)
            
        if score < self.min_score:
            return ExitSignal.full_exit(
                reason=f"MIN_SCORE (점수 {score:.2f} < {self.min_score})",
                price=context.current_price
            )
        return ExitSignal.hold()



def calculate_atr(data: 'pd.DataFrame', period: int = 14) -> 'pd.Series':
    """ATR (Average True Range) 계산
    
    Args:
        data: OHLC 데이터프레임
        period: ATR 기간 (기본값 14)
        
    Returns:
        ATR 시리즈
    """
    high = data['high']
    low = data['low']
    close = data['close']
    
    # True Range 계산
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = True Range의 지수이동평균
    atr = true_range.ewm(span=period, adjust=False).mean()
    
    return atr
