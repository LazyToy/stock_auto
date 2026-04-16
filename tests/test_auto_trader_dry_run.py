"""AutoTrader Dry Run Test Script

Mocks KISAPIClient to verify AutoTrader logic without real API calls.
"""

import sys
import os
import logging
from unittest.mock import MagicMock
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.append(r"d:\HY\develop_Project\stock_auto")

from src.data.api_client import KISAPIClient
from src.data.models import Account, Position
from src.trader.auto_trader import AutoTrader

# 로깅 설정
logging.basicConfig(level=logging.INFO)

def main():
    print("=== AutoTrader Dry Run Test ===")
    
    # 1. API Client Mocking
    mock_api = MagicMock(spec=KISAPIClient)
    
    # 계좌 잔고 Mocking
    mock_account = Account(
        account_number="12345678",
        cash=1000000.0, # 100만원 예수금
        positions=[
            # 기존 보유 종목 (삼성전자 10주)
            Position(symbol="005930.KS", quantity=10, avg_price=70000, current_price=75000)
        ]
    )
    mock_api.get_account_balance.return_value = mock_account
    
    # 주문 실행 Mocking
    mock_api.place_order.return_value = "TEST_ORDER_NO"
    
    # 2. AutoTrader 초기화
    # 테스트용 작은 Universe
    UNIVERSE = ["005930.KS", "000660.KS", "035420.KS"]
    
    trader = AutoTrader(
        api_client=mock_api,
        universe=UNIVERSE,
        max_stocks=2, # 상위 2개 종목만 선정
        dry_run=True
    )
    
    # 3. StockSelector Mocking (데이터 다운로드 시간 절약)
    # 실제 Selector를 쓰면 시간이 걸리므로, selector의 메서드만 살짝 Patch하거나
    # 아니면 그냥 실제 Selector가 돌아가는지 확인하기 위해 그대로 둠.
    # 여기서는 시간 절약을 위해 Selector의 select_top_n을 Mocking
    
    # trader.selector.select_top_n = MagicMock(return_value=[
    #     {'ticker': '000660.KS', 'score': 5.0, 'current_price': 120000}, # SK하이닉스 (매수 대상)
    #     {'ticker': '035420.KS', 'score': 4.0, 'current_price': 200000}  # NAVER (매수 대상)
    # ])
    # -> 실제 로직 검증을 위해 Mocking 하지 않고 실제 데이터로 돌려봄 (Hexa-Factor가 잘 계산되는지 확인)
    
    # 4. 실행
    print("\nRunning daily routine...")
    try:
        trader.run_daily_routine()
    except Exception as e:
        print(f"Error during execution: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Test Completed ===")
    
    # 검증
    # 1. 계좌 조회 호출 확인
    mock_api.get_account_balance.assert_called_once()
    print("Checked account balance: OK")
    
    # 2. 주문 로그 확인 (Mock 호출 기록)
    # 실제 selector 결과에 따라 다름.
    # 만약 삼성전자가 Top 2에 없으면 매도 주문이 나와야 함.
    # SK하이닉스, NAVER가 Top 2라면 매수 주문이 나와야 함.

if __name__ == "__main__":
    main()
