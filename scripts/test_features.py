"""기능 통합 테스트 (Integration Test)

구현된 새로운 기능들을 테스트합니다:
1. Google Gemini 기반 뉴스 감성 분석
2. Discord 알림 발송
3. WebSocket 연결 (비동기)
4. ML 모델 스케줄링 시뮬레이션
5. 포트폴리오 최적화 계산
"""

import sys
import os
import asyncio
import logging
import pandas as pd
import numpy as np

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.analysis.sentiment import SentimentAnalyzer
from src.utils.notification import send_notification
from src.data.websocket_client import KISWebSocketClient
from src.portfolio.optimizer import PortfolioOptimizer
from src.train.trainer import train_monthly_model

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestIntegration")

async def test_sentiment_analysis():
    logger.info("--- 1. 감성 분석 테스트 (Google Gemini) ---")
    analyzer = SentimentAnalyzer()
    
    # 예시: 삼성전자 (실제 뉴스는 API로 가져오지만 여기선 키워드 체크 또는 LLM 연결만 확인)
    score = analyzer.analyze_ticker("005930.KS")
    logger.info(f"삼성전자 분석 결과: {score}")
    
    # LLM 직접 테스트
    if analyzer.gemini_model:
        logger.info("Gemini 모델 호출 테스트...")
        test_titles = [
            "Earnings Surprise: Revenue up 20%",
            "CEO Resigns amid fraud scandal",
            "New product launch successful"
        ]
        llm_score = analyzer._analyze_with_llm(test_titles)
        logger.info(f"LLM 테스트 점수 (기대값: -0.5 ~ 0.5): {llm_score}")
    else:
        logger.warning("Gemini API Key가 설정되지 않았거나 초기화 실패")

async def test_notification():
    logger.info("--- 2. 알림 테스트 (Discord) ---")
    if Config.DISCORD_WEBHOOK_URL:
        success = send_notification("🔔 Stock Auto Trader 통합 테스트 알림입니다.")
        logger.info(f"알림 전송 결과: {success}")
    else:
        logger.warning("Discord Webhook URL이 설정되지 않음")

async def test_websocket():
    logger.info("--- 3. WebSocket 연결 테스트 ---")
    # 실제 연결은 오래 걸릴 수 있으므로, 객체 생성 및 시작 메서드 호출만 확인하고 3초 후 종료
    client = KISWebSocketClient(market="KR", event_callback=lambda x: print(f"WS Data: {x}"))
    
    # 비동기 시작
    task = asyncio.create_task(client.connect())
    
    await asyncio.sleep(3)
    client.running = False
    logger.info("WebSocket 테스트 종료")

def test_portfolio_optimization():
    logger.info("--- 4. 포트폴리오 최적화 테스트 ---")
    # 더미 데이터 생성
    dates = pd.date_range(start='2024-01-01', periods=100)
    data = {
        'AAPL': np.random.normal(0.001, 0.02, 100),
        'MSFT': np.random.normal(0.001, 0.015, 100),
        'GOOGL': np.random.normal(0.001, 0.025, 100)
    }
    df = pd.DataFrame(data, index=dates)
    
    optimizer = PortfolioOptimizer(df)
    weights = optimizer.optimize_sharpe_ratio()
    logger.info(f"최적 비중 (Sharpe): {weights}")

def test_training_pipeline():
    logger.info("--- 5. ML 학습 파이프라인 테스트 (Simulated) ---")
    # 실제 데이터 로드는 오래 걸리므로 로그만 확인
    try:
        train_monthly_model(market="KR", strategy_type="ml_rf")
        logger.info("학습 함수 실행 성공")
    except Exception as e:
        logger.error(f"학습 함수 실행 실패: {e}")

async def main():
    logger.info("=== 기능 통합 테스트 시작 ===")
    
    await test_sentiment_analysis()
    # await test_notification() # 알림이 실제로 가므로 주의
    await test_websocket()
    
    # 동기 함수 호출
    test_portfolio_optimization()
    test_training_pipeline()
    
    logger.info("=== 모든 테스트 완료 ===")

if __name__ == "__main__":
    asyncio.run(main())
