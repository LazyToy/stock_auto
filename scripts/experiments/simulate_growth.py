"""성장주 투자 전략 시뮬레이션 (Growth Strategy Simulator)

Value 모드와 Growth 모드의 종목 선정 결과를 비교합니다.
"""

import sys
import os
import pandas as pd

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.selector import StockSelector

def run_simulation():
    # 테스트 유니버스: 빅테크(우량주) + 고성장 기술주(Growth) + 적자 성장주
    universe = [
        # Big Tech (Value/Growth Hybrid)
        "AAPL", "MSFT", "GOOGL", "NVDA", 
        
        # Growth / Volatile
        "TSLA", "AMD", "PLTR", "SNOW", "DDOG", "CRWD", "NET", # Cloud/AI
        "COIN", "MSTR", # Crypto
        "IONQ", "JOBY", # Deep Tech
        
        # Value / Stable
        "KO", "JNJ", "PG", "BRK-B"
    ]
    
    print("=== 1. 가치주(VALUE) 모드 실행 ===")
    selector_value = StockSelector(universe, period='1y', benchmark='^GSPC', style='VALUE')
    selector_value.download_data() # 데이터 다운로드 추가
    df_value = selector_value.calculate_metrics()
    
    print("\n=== 2. 성장주(GROWTH) 모드 실행 ===")
    selector_growth = StockSelector(universe, period='1y', benchmark='^GSPC', style='GROWTH')
    selector_growth.download_data() # 데이터 다운로드 추가
    # 데이터 재다운로드 방지를 위해 기존 데이터 활용 가능하지만, 
    # 독립성을 위해 새로 생성 (캐싱 로직이 없으므로 다시 다운로드됨)
    df_growth = selector_growth.calculate_metrics()
    
    print("\n" + "="*60)
    print("📊 시뮬레이션 결과 비교")
    print("="*60)
    
    print("\n[가치주(VALUE) Top 5]")
    if not df_value.empty:
        cols = ['ticker', 'score', 'momentum', 'pe', 'revenue_growth', 'gpa']
        print(df_value[cols].head(5).to_string(index=False))
        
    print("\n[성장주(GROWTH) Top 5]")
    if not df_growth.empty:
        cols = ['ticker', 'score', 'momentum', 'pe', 'revenue_growth', 'psr']
        print(df_growth[cols].head(5).to_string(index=False))

    # 주요 차이점 분석
    if not df_value.empty and not df_growth.empty:
        top_val = set(df_value.head(5)['ticker'])
        top_gro = set(df_growth.head(5)['ticker'])
        
        print("\n[분석]")
        print(f"- Value 모드 전용 선정: {top_val - top_gro}")
        print(f"- Growth 모드 전용 선정: {top_gro - top_val}")
        print(f"- 공통 선정: {top_val & top_gro}")

if __name__ == "__main__":
    run_simulation()
