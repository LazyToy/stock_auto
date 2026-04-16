"""9-Factor Strategy Simulation Script

Verifies the enhanced StockSelector with 9 factors:
1. Momentum
2. Volatility
3. Volume Strength
4. Relative Strength
5. P/E (Valuation)
6. ROE (Profitability)
7. GPA (Quality) - NEW
8. Revenue Growth (Growth) - NEW
9. Debt Ratio (Stability) - NEW
"""

import sys
import os
import pandas as pd

# 프로젝트 루트 경로 추가
sys.path.append(r"d:\HY\develop_Project\stock_auto")

from src.strategies.selector import StockSelector

def main():
    # KOSPI & KOSDAQ 우량주 혼합 유니버스
    UNIVERSE = [
        "005930.KS", # 삼성전자
        "000660.KS", # SK하이닉스
        "035420.KS", # NAVER
        "035720.KS", # 카카오
        "068270.KS", # 셀트리온
        "005380.KS", # 현대차
        "000270.KS", # 기아
        "051910.KS", # LG화학
        "006400.KS", # 삼성SDI
        "005490.KS", # POSCO홀딩스
        "105560.KS", # KB금융
        "055550.KS", # 신한지주
        "086520.KQ", # 에코프로
        "247540.KQ", # 에코프로비엠
        "028300.KQ", # HLB
    ]
    
    print("="*60)
    print("Running 9-Factor Strategy Simulation")
    print("="*60)
    
    selector = StockSelector(tickers=UNIVERSE, period="6mo")
    selector.download_data()
    
    print("\nCalculating 9-Factor Metrics...")
    results = selector.calculate_metrics()
    
    if results.empty:
        print("No results calculated.")
        return
        
    print("\n[Top 10 Ranked Stocks with Deep Research Factors]")
    
    # 출력 컬럼 정리
    cols = ['ticker', 'score', 'momentum', 'volatility', 'pe', 'roe', 'gpa', 'revenue_growth', 'debt_to_equity']
    
    # 보기 좋게 포맷팅
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    # 상위 10개 출력
    top_10 = results.head(10)[cols]
    print(top_10)
    
    print("\n" + "="*60)
    print("Analysis:")
    for _, row in top_10.iterrows():
        print(f"[{row['ticker']}] Score: {row['score']:.4f}")
        print(f"  > Quality (GPA): {row['gpa']}")
        print(f"  > Growth (Rev):  {row['revenue_growth']}")
        print(f"  > Stability (Debt): {row['debt_to_equity']}")
        print("-" * 30)

if __name__ == "__main__":
    main()
