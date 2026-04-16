"""중앙 설정 관리 모듈

환경 변수 로드 및 프로젝트 전반의 설정을 관리합니다.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    """설정 관리 클래스"""
    
    # 기본 경로
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    CONFIG_DIR = BASE_DIR / "config"
    LOG_DIR = BASE_DIR / "logs"
    
    # API 설정
    KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
    KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    KIS_ACCOUNT_NUMBER = os.getenv("KIS_ACCOUNT_NUMBER", "")
    KIS_ACCOUNT_PRODUCT_CODE = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")
    
    # 트레이딩 모드
    TRADING_MODE = os.getenv("TRADING_MODE", "mock").lower() # real / mock
    IS_MOCK = TRADING_MODE == "mock"
    
    # 텔레그램 설정
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Discord 설정
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    
    # URL 설정
    URL_REAL = "https://openapi.koreainvestment.com:9443"
    URL_MOCK = "https://openapivts.koreainvestment.com:29443"

    # LLM 설정 (Google Gemini)
    # GOOGLE_API_KEY: 레거시 단일 키 — 하위 호환 유지
    # 다중 키를 사용하려면 get_gemini_api_keys() 또는 GeminiKeyManager를 사용하세요.
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")

    # Reddit API 설정 (Social Analysis)
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "stock_auto_bot/1.0")

    
    @classmethod
    def get_gemini_api_keys(cls) -> List[str]:
        """설정된 모든 Gemini API 키 목록 반환.

        환경변수 GOOGLE_API_KEY_1, GOOGLE_API_KEY_2, ... 및 GOOGLE_API_KEY를
        모두 수집하여 빈 값/중복 제거 후 반환합니다.

        Returns:
            List[str]: 유효한 Gemini API 키 목록 (순서 보장)
        """
        from src.utils.gemini_key_manager import GeminiKeyManager
        return GeminiKeyManager()._load_keys()

    @classmethod
    def get_base_url(cls) -> str:
        """현재 모드에 따른 API Base URL 반환"""
        return cls.URL_MOCK if cls.IS_MOCK else cls.URL_REAL

    @classmethod
    def load_universe(cls) -> Dict[str, List[str]]:
        """유니버스 종목 리스트 로드"""
        universe_path = cls.CONFIG_DIR / "universe.json"
        try:
            with open(universe_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"유니버스 설정 파일을 찾을 수 없습니다: {universe_path}")
            return {"KR": [], "US": []}
        except json.JSONDecodeError:
            logging.error(f"유니버스 설정 파일 형식이 잘못되었습니다: {universe_path}")
            return {"KR": [], "US": []}

    @classmethod
    def validate(cls):
        """필수 설정 확인"""
        missing = []
        if not cls.KIS_APP_KEY: missing.append("KIS_APP_KEY")
        if not cls.KIS_APP_SECRET: missing.append("KIS_APP_SECRET")
        if not cls.KIS_ACCOUNT_NUMBER: missing.append("KIS_ACCOUNT_NUMBER")

        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")


def normalize_ticker(ticker: str, market: str = "KR") -> str:
    """티커 형식 정규화

    KR 마켓: .KS / .KQ 접미사 제거
    US 마켓: 그대로 반환

    Args:
        ticker: 종목 코드 (예: '005930.KS', 'AAPL')
        market: 시장 구분 ('KR' 또는 'US')

    Returns:
        정규화된 티커 문자열
    """
    if market == "KR":
        return ticker.replace(".KS", "").replace(".KQ", "")
    return ticker

# 디렉토리 생성
Config.LOG_DIR.mkdir(exist_ok=True)
