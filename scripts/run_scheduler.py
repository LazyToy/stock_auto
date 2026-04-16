"""글로벌 자동 매매 시스템 실행 스크립트 (24시간 상시 가동)

한국 주식(KR)과 미국 주식(US)을 통합 관리하며,
장중에는 실시간 시세 감시 및 뉴스 감성 분석을 수행합니다.
"""

import time
import logging
from datetime import datetime
import sys
import os
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가 (상위 디렉토리)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# scripts 패키지 경로 추가 (scripts 내부 모듈 import 위함)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from run_trading import run_single_strategy
from src.data.api_client import KISAPIClient
from src.trader.auto_trader import AutoTrader
from src.train.trainer import train_monthly_model
from src.data.websocket_client import KISWebSocketClient
from src.config import Config
from src.utils.execution_mode import describe_execution_mode
from src.utils.runtime_clients import build_kis_client
from src.utils.runtime_logging import configure_script_logging


logger = logging.getLogger("GlobalTrader")
_LOGGING_CONFIGURED = False
DEFAULT_BROKER_IS_MOCK = True
DEFAULT_DRY_RUN = True


def configure_logging():
    """실행 시점에만 파일 로깅을 초기화한다."""
    global _LOGGING_CONFIGURED
    _LOGGING_CONFIGURED = configure_script_logging(
        file_name="global_trading.log",
        fmt='%(asctime)s - GLOBAL_BOT - %(levelname)s - %(message)s',
        configured=_LOGGING_CONFIGURED,
    )

def get_market_status(now):
    """현재 시간에 따른 시장 상태 및 타겟 시장 반환"""
    # 한국장: 평일 09:00 ~ 15:30
    if now.weekday() < 5 and (9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30)):
        return "KR", True
        
    # 미국장: 평일 23:30 ~ 06:00 (서머타임 미고려, 단순화)
    # (밤 11시 30분 ~ 다음날 아침 6시)
    is_us_time = (now.weekday() < 5 and now.hour >= 23 and now.minute >= 30) or \
                 (now.weekday() < 5 and now.hour < 6)
                 
    if is_us_time:
        return "US", True
        
    return None, False

def run_monitoring(market):
    """실시간 감시 및 뉴스 분석 실행"""
    try:
        load_dotenv()
        logger.info(f"[{market}] 실행 모드: {describe_execution_mode(DEFAULT_BROKER_IS_MOCK, DEFAULT_DRY_RUN)}")
        api_client = build_kis_client(
            app_key=Config.KIS_APP_KEY,
            app_secret=Config.KIS_APP_SECRET,
            account_number=Config.KIS_ACCOUNT_NUMBER,
            is_mock=DEFAULT_BROKER_IS_MOCK,
            market=market,
            client_cls=KISAPIClient,
        )
        
        # 모니터링용 Trader (유니버스는 불필요하므로 빈 리스트)
        trader = AutoTrader(api_client, universe=[], market=market, dry_run=DEFAULT_DRY_RUN)
        
        # 1. 실시간 시세 감시 (1분)
        trader.monitor_realtime()
        
        # 2. 뉴스 감성 분석 (매 시 정각)
        if datetime.now().minute == 0:
            trader.check_market_sentiment()
            
    except Exception as e:
        logger.error(f"[{market}] 모니터링 실패: {e}")

def main():
    configure_logging()
    logger.info("=== 🌍 글로벌 자동 매매 시스템 가동 (KR + US) ===")
    logger.info("모드: 24시간 상시 감시 + 자동 매매")
    
    # 작업 실행 여부 플래그 (중복 실행 방지)
    last_kr_run_date = None
    last_us_run_date = None
    last_train_run_month = None

    # WebSocket 클라이언트 시작 (KR/US) - 별도 스레드에서 실행됨
    ws_kr = KISWebSocketClient(market="KR", event_callback=lambda data: logger.debug(f"[WS] Data: {data}"))
    ws_kr.start()
    
    # ws_us = KISWebSocketClient(market="US") # 필요시 추가
    # ws_us.start()


    while True:
        now = datetime.now()
        
        # 1. 정규 매매 루틴 (Daily Job)
        # 한국장 시작 (09:30)
        if now.weekday() < 5 and now.hour == 9 and now.minute == 30 and last_kr_run_date != now.date():
            logger.info("☀️ 한국 주식 자동 매매 루틴 시작")
            logger.info("☀️ 한국 주식 자동 매매 루틴 시작")
            try:
                run_single_strategy(market="KR", strategy_type="momentum", dry_run=True, is_mock=DEFAULT_BROKER_IS_MOCK) # 기본값 모의투자
                last_kr_run_date = now.date()
                logger.info("☀️ 한국 주식 루틴 완료")
            except Exception as e:
                logger.error(f"한국 주식 루틴 실패: {e}")
            
        # 미국장 시작 (23:30)
        if now.weekday() < 5 and now.hour == 23 and now.minute == 30 and last_us_run_date != now.date():
            logger.info("🌙 미국 주식 자동 매매 루틴 시작")
            logger.info("🌙 미국 주식 자동 매매 루틴 시작")
            try:
                run_single_strategy(market="US", strategy_type="momentum", dry_run=True, is_mock=DEFAULT_BROKER_IS_MOCK) # 기본값 모의투자
                last_us_run_date = now.date()
                logger.info("🌙 미국 주식 루틴 완료")
            except Exception as e:
                logger.error(f"미국 주식 루틴 실패: {e}")

        # 2. 월간 모델 재학습 (매월 1일 자정)
        if now.day == 1 and now.hour == 0 and now.minute == 0 and last_train_run_month != now.month:
            logger.info("🔄 [Schedule] 월간 모델 재학습 시작")
            try:
                train_monthly_model(market="KR", strategy_type="ml_rf")
                train_monthly_model(market="US", strategy_type="ml_rf")
                last_train_run_month = now.month
            except Exception as e:
                logger.error(f"모델 재학습 스케줄 실패: {e}")

            
        # 3. 장중 실시간 감시 (Monitoring)
        # WebSocket이 실시간 시세를 처리하므로, 여기서는 뉴스 분석이나 포트폴리오 상태 체크 등 보조 업무 수행
        target_market, is_open = get_market_status(now)
        
        if is_open:
            # 기존 폴링 방식 모니터링은 유지하되, WebSocket과 충돌하지 않도록 조정
            # 지금은 뉴스 분석용으로만 호출
            run_monitoring(target_market)

        else:
            # 장 마감 시간대에는 매 시 정각에만 로그 출력 (로그 폭주 방지)
            if now.minute == 0 and now.second < 5:
                logger.info(f"현재 장 마감 상태입니다. (대기 중...)")
        
        # 1분 대기
        time.sleep(60)

if __name__ == "__main__":
    main()
