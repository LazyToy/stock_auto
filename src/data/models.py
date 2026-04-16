"""데이터 모델 정의

주가, 주문, 포지션, 계좌 등의 데이터 구조를 정의합니다.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderType(Enum):
    """주문 유형"""
    MARKET = "market"  # 시장가
    LIMIT = "limit"    # 지정가


class OrderSide(Enum):
    """주문 방향"""
    BUY = "buy"    # 매수
    SELL = "sell"  # 매도


@dataclass
class StockPrice:
    """주가 데이터
    
    Attributes:
        symbol: 종목 코드 (예: 005930)
        datetime: 일시
        open: 시가
        high: 고가
        low: 저가
        close: 종가
        volume: 거래량
    """
    symbol: str
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    def __post_init__(self) -> None:
        """데이터 유효성 검증"""
        if self.open < 0 or self.high < 0 or self.low < 0 or self.close < 0:
            raise ValueError("주가는 음수일 수 없습니다")
        if self.volume < 0:
            raise ValueError("거래량은 음수일 수 없습니다")


@dataclass
class Order:
    """주문 정보
    
    Attributes:
        symbol: 종목 코드
        order_type: 주문 유형 (시장가/지정가)
        side: 주문 방향 (매수/매도)
        quantity: 주문 수량
        price: 주문 가격 (시장가인 경우 None)
        created_at: 주문 생성 시각
        order_id: 주문 ID (체결 후 할당)
    """
    symbol: str
    order_type: OrderType
    side: OrderSide
    quantity: int
    price: Optional[float]
    created_at: datetime
    order_id: Optional[str] = None
    
    def __post_init__(self) -> None:
        """데이터 유효성 검증"""
        # 지정가 주문은 가격이 필수
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("지정가 주문은 가격이 필수입니다")
        
        if self.quantity <= 0:
            raise ValueError("주문 수량은 양수여야 합니다")
        
        # 지정가 주문 가격은 양수여야 합니다. 시장가 주문은 가격이 0일 수 있습니다.
        if self.price is not None and self.price <= 0 and self.order_type == OrderType.LIMIT:
            raise ValueError("지정가 주문 가격은 양수여야 합니다")



@dataclass
class Position:
    """포지션 정보
    
    Attributes:
        symbol: 종목 코드
        quantity: 보유 수량
        avg_price: 평균 매수 가격
        current_price: 현재 가격
        exchange: 거래소 코드 (KR, NASD, NYSE, AMEX)
    """
    symbol: str
    quantity: int
    avg_price: float
    current_price: float
    exchange: str = "KR"
    
    @property
    def unrealized_pnl(self) -> float:
        """평가 손익 (원화)"""
        return (self.current_price - self.avg_price) * self.quantity
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """평가 손익률 (%)"""
        if self.avg_price == 0:
            return 0.0
        return ((self.current_price - self.avg_price) / self.avg_price) * 100
    
    @property
    def market_value(self) -> float:
        """현재 시장 가치"""
        return self.current_price * self.quantity


@dataclass
class Account:
    """계좌 정보
    
    Attributes:
        account_number: 계좌 번호
        cash: 현금
        positions: 보유 포지션 목록
    """
    account_number: str
    cash: float
    positions: list[Position]
    
    @property
    def total_value(self) -> float:
        """총 자산 (현금 + 포지션 가치)"""
        positions_value = sum(pos.market_value for pos in self.positions)
        return self.cash + positions_value
    
    @property
    def total_unrealized_pnl(self) -> float:
        """전체 평가 손익"""
        return sum(pos.unrealized_pnl for pos in self.positions)
