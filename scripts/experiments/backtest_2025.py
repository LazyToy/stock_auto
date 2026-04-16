"""2025년 투자 시뮬레이션 (Backtest)

한국/미국 주식 각 100만원(약 $715)으로 시작하여
2025년 한 해 동안의 성과를 시뮬레이션합니다.

전략:
- 월간 리밸런싱 (매월 첫 거래일)
- 팩터: 6개월 모멘텀 / 6개월 변동성 (Risk-Adjusted Momentum)
- 유니버스: 대표 우량주 (Config에서 로드)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import argparse
import sys
import os
from datetime import datetime, timedelta

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config

def get_monthly_price(ticker, start_date, end_date):
    """월별 수정 주가 데이터 조회"""
    df = yf.download(ticker, start=start_date, end=end_date, interval="1d", progress=False)
    if df.empty:
        return None
    # 월말/월초 데이터로 리샘플링 (여기서는 일별 데이터 전체 사용 후 로직에서 필터링)
    return df['Adj Close']

def calculate_score(price_series, date):
    """특정 날짜 기준 6개월 모멘텀/변동성 점수 계산"""
    # date 기준 6개월 전 (~126 거래일)
    try:
        # loc는 정확한 날짜가 없으면 에러나므로, date 이전 데이터만 슬라이싱
        history = price_series.loc[:date].tail(130) # 넉넉히 가져옴
        if len(history) < 100: # 데이터 부족
            return -np.inf
            
        current_price = history.iloc[-1]
        past_price = history.iloc[-126] # 약 6개월 전
        
        # 모멘텀
        momentum = (current_price - past_price) / past_price
        
        # 변동성 (일일 수익률의 표준편차 * sqrt(252))
        daily_ret = history.pct_change().dropna()
        volatility = daily_ret.std() * np.sqrt(252)
        
        if volatility == 0:
            return 0
            
        return momentum / volatility
    except Exception as e:
        return -np.inf

def run_backtest(market, capital, universe, start_date=None, end_date=None):
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    print(f"\n[{market} Market Backtest Start...]")
    print(f"Initial Capital: {capital:,.0f}")

    data = {}
    print("Downloading data...")
    for ticker in universe:
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False, multi_level_index=False) # multi_level_index=False for simpler DF
            
            if df.empty:
                print(f"Warning: No data for {ticker}")
                continue
                
            # print(f"{ticker} columns: {df.columns}")
            
            if 'Adj Close' in df.columns:
                data[ticker] = df['Adj Close']
            elif 'Close' in df.columns:
                data[ticker] = df['Close']
            else:
                print(f"Warning: No price data for {ticker}")
            
            data[ticker] = data[ticker].ffill()
            
        except Exception as e:
            print(f"Error downloading {ticker}: {e}")
            continue
                
    # 데이터프레임 통합
    if not data:
        print("No data available for backtest.")
        return [], 0.0

    price_df = pd.DataFrame(data)
    price_df = price_df.ffill()
    
    # 2. 월별 리밸런싱 날짜 생성 (매월 첫 거래일)
    dates = pd.date_range(start=start_date, end=end_date, freq='BMS') # Business Month Start
    
    portfolio_value = [capital]
    history = []
    
    current_cash = capital
    holdings = {} # {ticker: quantity}
    
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        
        # 해당 날짜가 price_df에 없으면 가장 가까운 이전 날짜 찾기
        if date not in price_df.index:
            idx = price_df.index.searchsorted(date)
            if idx >= len(price_df):
                current_date = price_df.index[-1]
            else:
                current_date = price_df.index[idx]
        else:
            current_date = date
            
        print(f"--- Rebalancing: {current_date.strftime('%Y-%m-%d')} ---")
        
        # 1. 평가 (자산 가치 업데이트)
        total_value = current_cash
        for ticker, qty in holdings.items():
            if ticker in price_df.columns:
                price = price_df.loc[current_date, ticker]
                total_value += price * qty
        
        # 2. 스코어링 및 선정
        scores = []
        for ticker in universe:
            if ticker not in price_df.columns: continue
            score = calculate_score(price_df[ticker], current_date)
            scores.append((ticker, score))
            
        scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = scores[:3] # Top 3 선정
        selected_tickers = [x[0] for x in top_stocks]
        
        print(f"Top 3: {selected_tickers}")
        
        # 3. 매매 (전량 매도 후 리밸런싱)
        # 실제로는 수수료 고려해야 하지만 여기선 생략
        current_cash = total_value
        holdings = {}
        
        target_amount = current_cash / 3
        for ticker in selected_tickers:
            price = price_df.loc[current_date, ticker]
            qty = int(target_amount // price)
            if qty > 0:
                holdings[ticker] = qty
                current_cash -= qty * price
                
        # 현재 가치 기록
        portfolio_value.append(total_value)
        history.append({
            'date': current_date,
            'total_value': total_value,
            'holdings': selected_tickers
        })
        
    # 최종 결과
    final_value = portfolio_value[-1]
    ret = (final_value - capital) / capital * 100
    print(f"Final Value: {final_value:,.0f} (Return: {ret:.2f}%)")
    
    return history, ret

def main():
    parser = argparse.ArgumentParser(description="2025 Stock Trading Backtest Simulation")
    parser.add_argument("--capital-kr", type=int, default=1_000_000, help="Initial capital for KR market")
    parser.add_argument("--capital-us", type=int, default=715, help="Initial capital for US market (USD)")
    args = parser.parse_args()

    # Config에서 Universe 로드
    universe_config = Config.load_universe()
    kr_universe = universe_config.get("KR", [])
    us_universe = universe_config.get("US", [])
    
    if not kr_universe or not us_universe:
        print("Error: Universe configuration missing in config/universe.json")
        return

    print("="*50)
    print("🚀 2025 Stock Trading Backtest Simulation")
    print("="*50)
    
    # KR Backtest
    kr_history, kr_ret = run_backtest("KR", args.capital_kr, kr_universe)
    
    print("-" * 30)
    
    # US Backtest
    us_history, us_ret = run_backtest("US", args.capital_us, us_universe)
    
    print("="*50)
    print(" [Summary]")
    print(f"🇰🇷 KR Market Return: {kr_ret:.2f}% ({args.capital_kr:,.0f} -> {args.capital_kr * (1+kr_ret/100):,.0f}원)")
    print(f"🇺🇸 US Market Return: {us_ret:.2f}% (${args.capital_us:,.0f} -> ${args.capital_us * (1+us_ret/100):,.2f})")
    
    # 환율 가정 (1400원)
    exchange_rate = 1400
    total_initial = args.capital_kr + (args.capital_us * exchange_rate)
    total_final = (args.capital_kr * (1+kr_ret/100)) + ((args.capital_us * (1+us_ret/100)) * exchange_rate)
    total_ret = (total_final - total_initial) / total_initial * 100
    
    print(f"💰 Total Return: {total_ret:.2f}% (Est. KRW, Rate: {exchange_rate})")
    print("="*50)

if __name__ == "__main__":
    main()
