"""기본 전략 인터페이스

모든 매매 전략이 상속받아야 하는 추상 클래스입니다.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any


class BaseStrategy(ABC):
    """모든 전략의 기본 인터페이스
    
    모든 커스텀 전략은 이 클래스를 상속받아야 합니다.
    """
    
    def __init__(self, name: str):
        """초기화
        
        Args:
            name: 전략 이름
        """
        self.name = name
        self.parameters: Dict[str, Any] = {}
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """매매 신호 생성
        
        Args:
            data: 주가 데이터 (datetime, open, high, low, close, volume 컬럼 필수)
            
        Returns:
            신호 데이터프레임 (signal, position 컬럼 포함)
            - signal: -1 (매도), 0 (보류), 1 (매수)
            - position: 누적 포지션
        """
        pass
    
    def validate_data(self, data: pd.DataFrame) -> None:
        """데이터 유효성 검증
        
        Args:
            data: 검증할 데이터
            
        Raises:
            ValueError: 필수 컬럼이 없는 경우
        """
        required_columns = ['close']
        missing = [col for col in required_columns if col not in data.columns]
        
        if missing:
            raise ValueError(f"필수 컬럼 누락: {missing}")
        
        if len(data) == 0:
            raise ValueError("데이터가 비어있습니다")
    
    def __repr__(self) -> str:
        """문자열 표현"""
        params_str = ', '.join(f"{k}={v}" for k, v in self.parameters.items())
        return f"{self.name}({params_str})"
