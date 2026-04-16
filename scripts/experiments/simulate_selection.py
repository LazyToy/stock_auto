"""종목 선정 시뮬레이션 스크립트

상위 30개 KOSPI 종목 중
모멘텀/변동성 점수가 높은 5개 종목을 선정하여
각각 200/5 = 40만원씩 분산 투자하는 시뮬레이션입니다.
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 프로젝트 루트 경로 추가
sys.path.append(r"d:\HY\develop_Project\stock_auto")

from src.strategies.selector import StockSelector

def main():
    # KOSPI 상위 30개 종목 (예시)
    UNIVERSE = [
        "005930.KS", # 삼성전자
        "000660.KS", # SK하이닉스
        "373220.KS", # LG에너지솔루션
        "207940.KS", # 삼성바이오로직스
        "005380.KS", # 현대차
        "000270.KS", # 기아
        "068270.KS", # 셀트리온
        "005490.KS", # POSCO홀딩스
        "035420.KS", # NAVER
        "006400.KS", # 삼성SDI
        "051910.KS", # LG화학
        "035720.KS", # 카카오
        "105560.KS", # KB금융
        "055550.KS", # 신한지주
        "012330.KS", # 현대모비스
        # ... 추가 가능
    ]
    
    print("="*50)
    print("Running Stock Selection Simulation")
    print("Strategy: Risk-Adjusted Momentum (Return / Volatility)")
    print("Universe: Top KOSPI Stocks")
    print("="*50)
    
    # 1. 과거 데이터로 종목 선정 (6개월 전 ~ 현재)
    # 실제로는 6개월 전 시점에서 6개월치 데이터를 보고 선정해야 함
    # 여기서는 간단히 최근 6개월 데이터로 '현재 시점'에서 가장 좋은 종목을 뽑는 로직 시연
    
    selector = StockSelector(tickers=UNIVERSE, period="6mo")
    selector.download_data()
    
    # 지표 계산
    results = selector.calculate_metrics()
    
    if results.empty:
        print("No results calculated.")
        return
        
    print("\n[Top 10 Ranked Stocks]")
    print(results.head(10)[['ticker', 'momentum', 'volatility', 'score']])
    
    # 상위 5개 선정
    top_5 = selector.select_top_n(5)
    
    print("\n" + "="*50)
    print("Selected Portfolio (Top 5)")
    print("="*50)
    
    total_capital = 2000000.0
    allocation_per_stock = total_capital / 5
    
    portfolio_value = 0
    
    for stock in top_5:
        ticker = stock['ticker']
        price = stock['current_price']
        momentum = stock['momentum']
        volatility = stock['volatility']
        
        # 매수 수량 계산
        quantity = int(allocation_per_stock // price)
        invested_amount = quantity * price
        
        print(f"Ticker: {ticker}")
        print(f"  - Momentum (6mo): {momentum*100:.2f}%")
        print(f"  - Volatility: {volatility:.4f}")
        print(f"  - Score: {stock['score']:.4f}")
        print(f"  - Price: {price:,.0f} KRW")
        print(f"  - Buy Quantity: {quantity}")
        print(f"  - Invested: {invested_amount:,.0f} KRW")
        print("-" * 30)
        
        portfolio_value += invested_amount
        
    print("="*50)
    print(f"Total Invested: {portfolio_value:,.0f} KRW")
    print(f"Cash Remaining: {total_capital - portfolio_value:,.0f} KRW")
    print("="*50)
    
    print("\n* Note: This simulation selects stocks based on RECENT performance.")
    print("* To perform a true backtest, we would need to select stocks based on data PRIOR to the simulation period.")
    print("* However, this demonstrates the selection logic successfully.")

if __name__ == "__main__":
    main()
