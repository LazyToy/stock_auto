import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta

class MarketDataFetcher:
    """
    시장 레짐 감지를 위한 데이터 수집 및 전처리 클래스
    """
    def __init__(self):
        # 기본 감지 대상 지수
        # ^GSPC: S&P 500
        # ^KS200: KOSPI 200
        # ^VIX: CBOE Volatility Index
        self.tickers = ['^GSPC', '^KS200', '^VIX']
        
    def fetch_history(self, symbol: str, period: str = "2y") -> pd.DataFrame:
        """
        특정 심볼의 과거 데이터 수집
        Args:
            symbol: yfinance 티커 (예: ^GSPC)
            period: 수집 기간 (예: 1y, 2y, max)
        Returns:
            pd.DataFrame: OHLCV 데이터
        """
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        return df

    def calculate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        레짐 감지에 필요한 파생 변수 계산
        - Daily Return (일일 수익률)
        - Volatility (20일 이동 표준편차)
        - Trend (50일 이동평균 대비 현재가 괴리율)
        """
        if df.empty:
            return pd.DataFrame()
            
        df = df.copy()
        
        # 1. 일일 수익률 (로그 수익률 권장하나, 여기선 단순 수익률 사용)
        df['daily_return'] = df['Close'].pct_change()
        
        # 2. 변동성 (20일 롤링 표준편차)
        df['volatility'] = df['daily_return'].rolling(window=20).std()
        
        # 3. 추세 (현재가 / 50일 이동평균 - 1)
        df['ma50'] = df['Close'].rolling(window=50).mean()
        df['trend'] = (df['Close'] / df['ma50']) - 1
        
        # 결측치 제거
        df.dropna(inplace=True)
        return df

    def get_regime_input_data(self) -> pd.DataFrame:
        """
        HMM 모델 학습/추론을 위한 통합 데이터셋 생성
        주로 S&P 500의 변동성과 수익률을 사용 (글로벌 기준)
        Returns:
            pd.DataFrame: ['daily_return', 'volatility'] 컬럼을 가진 데이터프레임
        """
        # MVP: S&P 500 기준 (가장 데이터 신뢰성 높음)
        # 추후 KOSPI 200 등 멀티 인덱스 확장 가능
        spy = self.fetch_history("^GSPC", period="2y")
        spy_features = self.calculate_features(spy)
        
        if spy_features.empty:
            return pd.DataFrame()
            
        # HMM 입력용 데이터 (수익률, 변동성)
        # 스케일링은 여기서 하지 않고 모델 파이프라인에서 할 수도 있으나,
        # 일단 원본 데이터를 반환
        return spy_features[['daily_return', 'volatility', 'trend']]
