"""리스크 관리자

주문 실행 전 리스크를 체크하고 관리합니다.
"""

from dataclasses import dataclass
from src.data.models import Order, OrderSide


class RiskManager:
    """리스크 관리자"""
    
    def __init__(
        self, 
        max_position_size: float = 10000000, 
        max_daily_loss: float = 1000000
    ):
        """초기화
        
        Args:
            max_position_size: 종목당 최대 투자 금액
            max_daily_loss: 일일 최대 손실 한도
        """
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        
    def check_order(self, order: Order, current_positions_value: float) -> bool:
        """주문 리스크 체크
        
        Args:
            order: 주문 정보
            current_positions_value: 현재 보유 포지션 가치
            
        Returns:
            승인 여부 (True/False)
        """
        if order.side == OrderSide.BUY:
            # 주문 금액 계산 (시장가는 대략적 계산 필요하나, 여기선 price가 있다고 가정하거나 별도 처리)
            price = order.price if order.price else 0 # 시장가 처리는 복잡하므로 일단 0이면 패스하거나 별도 로직
            if price == 0:
                pass # 시장가 주문 시 현재가를 알아야 정확함. 여기선 단순화.

            order_amount = price * order.quantity
            
            # 1. 종목당 최대 투자 금액 체크
            if current_positions_value + order_amount > self.max_position_size:
                return False
                
        return True

    def check_daily_loss(self, current_daily_loss: float) -> bool:
        """일일 손실 한도 체크
        
        Args:
            current_daily_loss: 현재 일일 손실액 (양수)
            
        Returns:
            거래 가능 여부 (True: 가능, False: 중단)
        """
        if current_daily_loss >= self.max_daily_loss:
            return False
        return True
