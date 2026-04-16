"""데이터 모델 테스트

TDD: 먼저 테스트를 작성하여 데이터 모델의 동작을 정의합니다.
"""

import pytest
from datetime import datetime
from decimal import Decimal


def test_stock_price_creation():
    """주가 데이터 생성 테스트"""
    from src.data.models import StockPrice
    
    # 주가 데이터 생성
    price = StockPrice(
        symbol="005930",  # 삼성전자
        datetime=datetime(2024, 1, 2, 9, 0),
        open=75000,
        high=76000,
        low=74500,
        close=75800,
        volume=10000000
    )
    
    # 검증
    assert price.symbol == "005930"
    assert price.open == 75000
    assert price.close == 75800
    assert price.volume == 10000000


def test_stock_price_validation():
    """주가 데이터 유효성 검증 테스트"""
    from src.data.models import StockPrice
    
    # 음수 가격은 에러 발생
    with pytest.raises(ValueError):
        StockPrice(
            symbol="005930",
            datetime=datetime(2024, 1, 2, 9, 0),
            open=-1000,  # 음수 가격
            high=76000,
            low=74500,
            close=75800,
            volume=10000000
        )


def test_order_creation():
    """주문 데이터 생성 테스트"""
    from src.data.models import Order, OrderType, OrderSide
    
    # 매수 주문 생성
    order = Order(
        symbol="005930",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=10,
        price=None,  # 시장가 주문은 가격 없음
        created_at=datetime.now()
    )
    
    # 검증
    assert order.symbol == "005930"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.quantity == 10


def test_limit_order_requires_price():
    """지정가 주문은 가격이 필수"""
    from src.data.models import Order, OrderType, OrderSide
    
    # 지정가 주문인데 가격이 없으면 에러
    with pytest.raises(ValueError):
        Order(
            symbol="005930",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=10,
            price=None,  # 지정가인데 가격이 없음
            created_at=datetime.now()
        )


def test_position_creation():
    """포지션 데이터 생성 테스트"""
    from src.data.models import Position
    
    # 포지션 생성
    position = Position(
        symbol="005930",
        quantity=100,
        avg_price=75000,
        current_price=76000
    )
    
    # 검증
    assert position.symbol == "005930"
    assert position.quantity == 100
    assert position.avg_price == 75000
    assert position.unrealized_pnl == (76000 - 75000) * 100  # 평가손익


def test_position_pnl_calculation():
    """포지션 평가손익 계산 테스트"""
    from src.data.models import Position
    
    # 수익 포지션
    profit_position = Position(
        symbol="005930",
        quantity=100,
        avg_price=75000,
        current_price=80000
    )
    assert profit_position.unrealized_pnl == 500000  # (80000 - 75000) * 100
    assert profit_position.unrealized_pnl_pct == pytest.approx(6.67, rel=0.1)  # 약 6.67%
    
    # 손실 포지션
    loss_position = Position(
        symbol="005930",
        quantity=100,
        avg_price=75000,
        current_price=70000
    )
    assert loss_position.unrealized_pnl == -500000  # (70000 - 75000) * 100
    assert loss_position.unrealized_pnl_pct == pytest.approx(-6.67, rel=0.1)


def test_account_creation():
    """계좌 정보 생성 테스트"""
    from src.data.models import Account, Position
    
    # 계좌 생성
    account = Account(
        account_number="12345678",
        cash=10000000,
        positions=[]
    )
    
    # 검증
    assert account.account_number == "12345678"
    assert account.cash == 10000000
    assert account.total_value == 10000000  # 포지션 없으면 현금만
    
    # 포지션 추가
    position = Position(
        symbol="005930",
        quantity=100,
        avg_price=75000,
        current_price=76000
    )
    account.positions.append(position)
    
    # 총 자산 = 현금 + 포지션 가치
    expected_total = 10000000 + (76000 * 100)
    assert account.total_value == expected_total
