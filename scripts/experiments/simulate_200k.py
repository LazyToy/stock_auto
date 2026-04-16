import sys
import os
from datetime import datetime
import pandas as pd
import yfinance as yf

# 프로젝트 루트 경로 추가
sys.path.append(r"d:\HY\develop_Project\stock_auto")

from src.backtest.engine import BacktestEngine, BacktestResult
from src.data.models import OrderSide
from src.strategies.multi_indicator import MultiIndicatorStrategy

class CustomBacktestEngine(BacktestEngine):
    def __init__(self, start_date, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_date = start_date

    def run(self) -> BacktestResult:
        # 전략 신호 생성
        signals = self.strategy.generate_signals(self.data)
        
        # 데이터 순회하며 시뮬레이션
        for i in range(len(self.data)):
            date = self.data['datetime'].iloc[i]
            price = self.data['close'].iloc[i]
            signal = signals['signal'].iloc[i]
            
            # 현재가 업데이트
            self.portfolio.update_market_value({self.symbol: price})

            # 지정된 시작 날짜 이전에는 매매 건너뛰기
            if date < self.start_date:
                continue

            # 신호 처리
            if signal == 1:  # 매수 신호
                # 가용 자금의 95% 투자
                target_amount = self.portfolio.cash * 0.95
                quantity = int(target_amount // price)
                
                if quantity > 0:
                    try:
                        self.portfolio.update_position(
                            self.symbol, quantity, price, OrderSide.BUY, date
                        )
                    except ValueError:
                        pass # 자금 부족 등은 무시하고 진행
                        
            elif signal == -1:  # 매도 신호
                if self.symbol in self.portfolio.positions:
                    quantity = self.portfolio.positions[self.symbol].quantity
                    if quantity > 0:
                        self.portfolio.update_position(
                            self.symbol, quantity, price, OrderSide.SELL, date
                        )
            
            # 일별 기록
            self.portfolio.record_history(date)
            
        return self._calculate_performance()

def main():
    # 데이터 다운로드 (삼성전자)
    ticker = "005930.KS"
    simulation_start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_data_date = (simulation_start_date.replace(year=simulation_start_date.year - 1)).strftime("%Y-%m-%d")
    
    print(f"Downloading data for {ticker}...")
    # auto_adjust=False로 설정하여 원본 컬럼 유지 시도
    df = yf.download(ticker, start=start_data_date, progress=False, auto_adjust=False)
    
    if len(df) == 0:
        print("Error: No data downloaded.")
        return

    # 컬럼 전처리 (Robust handling)
    # MultiIndex 컬럼인 경우 레벨 0만 사용
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 인덱스를 컬럼으로 변환 ('Date'가 컬럼이 됨)
    df.reset_index(inplace=True)
    
    # 모든 컬럼명 소문자로 변환 및 문자열 변환
    df.columns = [str(col).lower() for col in df.columns]
    
    # 'date'를 'datetime'으로 변경
    if 'date' in df.columns:
        df.rename(columns={'date': 'datetime'}, inplace=True)
    
    # 필수 컬럼 확인
    required_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        print(f"Error: Missing columns: {missing_cols}")
        print(f"Current columns: {df.columns.tolist()}")
        print(df.head())
        return

    # adj close가 있으면 close로 사용하거나, close가 있으면 그대로 사용
    # yfinance 기본 다운로드는 'Adj Close'와 'Close'를 모두 줄 수 있음
    if 'adj close' in df.columns and 'close' not in df.columns:
        df.rename(columns={'adj close': 'close'}, inplace=True)

    print(f"Data downloaded: {len(df)} rows")
    print(f"Columns: {df.columns.tolist()}")
    
    # 전략 초기화
    strategy = MultiIndicatorStrategy()
    
    # 엔진 초기화
    engine = CustomBacktestEngine(
        start_date=simulation_start_date,
        strategy=strategy,
        symbol=ticker,
        data=df,
        initial_capital=2000000.0  # 200만원 (float)
    )
    
    # 실행
    print("Running simulation...")
    result = engine.run()
    
    # 결과 출력
    print("\n" + "="*50)
    print(f"Simulation Result (From {simulation_start_date.date()})")
    print("="*50)
    print(f"Initial Capital: {engine.initial_capital:,.0f} KRW")
    print(f"Final Value:    {result.portfolio.total_value:,.0f} KRW")
    print(f"Total Return:   {result.total_return:.2f}%")
    print(f"CAGR:           {result.cagr:.2f}%")
    print(f"Sharpe Ratio:   {result.sharpe_ratio:.2f}")
    print(f"Max Drawdown:   {result.max_drawdown:.2f}%")
    print("-"*50)
    print("Trade History:")
    if not result.trades:
        print("No trades executed.")
    for trade in result.trades:
        print(f"[{trade.timestamp.date()}] {trade.side.name} {trade.quantity} shares @ {trade.price:,.0f} KRW")
    print("="*50)

if __name__ == "__main__":
    main()
