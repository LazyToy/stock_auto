"""자동 매매 시스템 실행 스크립트

이 스크립트는 AutoTrader를 초기화하고 매일 정해진 시간에 매매 루틴을 실행합니다.
"""

import sys
import os
import time
import schedule
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
sys.path.append(r"d:\HY\develop_Project\stock_auto")

from src.data.api_client import KISAPIClient
from src.trader.auto_trader import AutoTrader
from src.config import Config
from src.utils.execution_mode import describe_execution_mode
from src.utils.runtime_clients import build_kis_client

# 환경 변수 로드
load_dotenv()
DEFAULT_BROKER_IS_MOCK = True
DEFAULT_DRY_RUN = True

def kr_trading_job():
    try:
        print(f"=== [KR] 국내 주식 자동 매매 루틴 시작 ({datetime.now()}) ===")
        print(f"실행 모드: {describe_execution_mode(DEFAULT_BROKER_IS_MOCK, DEFAULT_DRY_RUN)}")

        # 1. 설정 로드
        APP_KEY = Config.KIS_APP_KEY
        APP_SECRET = Config.KIS_APP_SECRET
        ACCOUNT_NO = Config.KIS_ACCOUNT_NUMBER

        if not all([APP_KEY, APP_SECRET, ACCOUNT_NO]):
            print("Error: .env 파일에 API 키 설정이 필요합니다.")
            return

        # 2. 투자 유니버스 설정 (config/universe.json에서 로드)
        UNIVERSE = Config.load_universe().get("KR", [])
        if not UNIVERSE:
            raise ValueError("유니버스 설정이 없습니다. config/universe.json에서 'KR' 키를 확인하세요.")
        
        # 3. 클라이언트 및 트레이더 초기화
        # 모의투자(True) 또는 실전투자(False) 설정
        IS_MOCK = DEFAULT_BROKER_IS_MOCK
        
        api_client = build_kis_client(
            app_key=APP_KEY,
            app_secret=APP_SECRET,
            account_number=ACCOUNT_NO,
            is_mock=IS_MOCK,
            market="KR",
            client_cls=KISAPIClient,
        )
        
        auto_trader = AutoTrader(
            api_client=api_client,
            universe=UNIVERSE,
            max_stocks=5,
            dry_run=DEFAULT_DRY_RUN, # 처음에는 안전하게 Dry Run으로 시작
            market="KR"
        )
        
        # 4. 루틴 실행
        auto_trader.run_daily_routine()
        print(f"=== [KR] 루틴 종료 ===")
        
    except Exception as e:
        print(f"[KR] 오류 발생: {e}")

def main():
    print("=== 국내 주식 자동 매매 스케줄러 시작 ===")
    print(f"실행 모드: {describe_execution_mode(DEFAULT_BROKER_IS_MOCK, DEFAULT_DRY_RUN)}")
    
    # 매일 평일 오전 9시 30분에 실행
    schedule.every().monday.at("09:30").do(kr_trading_job)
    schedule.every().tuesday.at("09:30").do(kr_trading_job)
    schedule.every().wednesday.at("09:30").do(kr_trading_job)
    schedule.every().thursday.at("09:30").do(kr_trading_job)
    schedule.every().friday.at("09:30").do(kr_trading_job)
    
    # 테스트를 위해 즉시 1회 실행
    # kr_trading_job()
    
    # 메인 루프
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    load_dotenv()
    main()
