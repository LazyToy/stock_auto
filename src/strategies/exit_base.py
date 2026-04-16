"""Exit 전략 기본 인터페이스

모든 청산(Exit) 전략이 상속받아야 하는 추상 클래스입니다.
Stop Loss, Trailing Stop, Take Profit 등의 청산 전략을 정의합니다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any
import pandas as pd


@dataclass
class ExitSignal:
    """Exit 신호 데이터"""
    should_exit: bool           # 청산 여부
    exit_ratio: float           # 청산 비율 (0.0~1.0, 부분 청산 지원)
    reason: str                 # 청산 사유
    price: Optional[float] = None  # 청산 가격 (지정가 주문용)
    
    @classmethod
    def hold(cls) -> 'ExitSignal':
        """보유 유지 신호"""
        return cls(should_exit=False, exit_ratio=0.0, reason="HOLD")
    
    @classmethod
    def full_exit(cls, reason: str, price: float = None) -> 'ExitSignal':
        """전량 청산 신호"""
        return cls(should_exit=True, exit_ratio=1.0, reason=reason, price=price)
    
    @classmethod
    def partial_exit(cls, ratio: float, reason: str, price: float = None) -> 'ExitSignal':
        """부분 청산 신호"""
        return cls(should_exit=True, exit_ratio=min(max(ratio, 0.0), 1.0), 
                   reason=reason, price=price)


@dataclass
class PositionContext:
    """포지션 컨텍스트 정보"""
    symbol: str                     # 종목 코드
    quantity: int                   # 보유 수량
    avg_price: float               # 평균 매수 단가
    current_price: float           # 현재가
    high_water_mark: float = 0.0   # 최고가 (Trailing Stop용)
    atr: float = 0.0               # ATR 값 (변동성 기반 전략용)
    holding_days: int = 0          # 보유 일수
    entry_date: Optional[Any] = None  # 진입일 (datetime or pd.Timestamp)
    current_score: float = 5.0    # 현재 종합 점수 (5.0은 중립/미평가)

    
    @property
    def profit_pct(self) -> float:
        """수익률 (%)"""
        if self.avg_price <= 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price
    
    @property
    def loss_pct(self) -> float:
        """손실률 (%) - 음수는 손실"""
        return self.profit_pct
    
    @property
    def drop_from_hwm(self) -> float:
        """고점 대비 하락률"""
        if self.high_water_mark <= 0:
            return 0.0
        return (self.current_price - self.high_water_mark) / self.high_water_mark


class BaseExitStrategy(ABC):
    """Exit 전략의 기본 인터페이스
    
    모든 청산 전략은 이 클래스를 상속받아야 합니다.
    """
    
    def __init__(self, name: str):
        """초기화
        
        Args:
            name: 전략 이름
        """
        self.name = name
        self.parameters: Dict[str, Any] = {}
    
    @abstractmethod
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """청산 조건 체크
        
        Args:
            context: 포지션 컨텍스트 정보
            market_data: 현재 시장 데이터 (OHLCV)
            
        Returns:
            ExitSignal: 청산 신호 (should_exit, exit_ratio, reason)
        """
        pass
    
    def reset(self) -> None:
        """전략 상태 초기화 (새 포지션 진입 시)"""
        pass
    
    def update(self, context: PositionContext, market_data: 'pd.Series') -> None:
        """상태 업데이트 (매 틱/봉마다 호출)
        
        Trailing Stop의 고점 갱신 등에 사용
        """
        pass
    
    def __repr__(self) -> str:
        """문자열 표현"""
        params_str = ', '.join(f"{k}={v}" for k, v in self.parameters.items())
        return f"{self.name}({params_str})"


class CompositeExitStrategy(BaseExitStrategy):
    """복합 Exit 전략
    
    여러 Exit 전략을 조합하여 사용합니다.
    하나라도 청산 신호가 발생하면 청산합니다.
    """
    
    def __init__(self, strategies: list):
        """초기화
        
        Args:
            strategies: Exit 전략 리스트
        """
        super().__init__(name="Composite Exit")
        self.strategies = strategies
        self.parameters = {
            'strategy_count': len(strategies),
            'strategies': [s.name for s in strategies]
        }
    
    def check_exit(self, context: PositionContext, market_data: 'pd.Series') -> ExitSignal:
        """모든 전략 체크 후 첫 번째 청산 신호 반환"""
        for strategy in self.strategies:
            signal = strategy.check_exit(context, market_data)
            if signal.should_exit:
                return signal
        return ExitSignal.hold()


    
    def reset(self) -> None:
        """모든 전략 초기화"""
        for strategy in self.strategies:
            strategy.reset()
    
    def update(self, context: PositionContext, market_data: 'pd.Series') -> None:
        """모든 전략 업데이트"""
        for strategy in self.strategies:
            strategy.update(context, market_data)
