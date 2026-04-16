import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# DB 모듈 로드 시도
try:
    from src.utils.database import get_db, DatabaseManager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

def render_market_tab(state, currency_symbol, market_code="KR"):
    """시장 탭 (KR/US) 렌더링"""
    if not state:
        st.error("데이터가 없습니다. 봇이 실행 중인지 확인하세요.")
        return

    # 주요 지표 카드
    c1, c2, c3 = st.columns(3)
    total_asset = state.get('total_asset')
    deposit = state.get('deposit')
    c1.metric("총 자산", f"{currency_symbol}{total_asset:,}" if total_asset is not None else "—")
    c2.metric("예수금", f"{currency_symbol}{deposit:,}" if deposit is not None else "—")
    c3.metric("투자 스타일", state.get('style', 'VALUE'))
    
    st.divider()
    
    # 보유 종목 포트폴리오
    st.subheader("💼 Portfolio Holdings")
    
    stocks = state.get('stocks', [])
    if stocks:
        df = pd.DataFrame(stocks)
        
        # 시각화용 데이터 가공
        df['price'] = df['current_price'].astype(float)
        df['avg'] = df['avg_price'].astype(float)
        df['qty'] = df['quantity'].astype(int)
        
        df['Current Value'] = df['price'] * df['qty']
        
        # 0으로 나누기 방지
        df['Profit %'] = df.apply(lambda row: ((row['price'] - row['avg']) / row['avg'] * 100) if row['avg'] > 0 else 0, axis=1)
        
        # 1. 보유 비중 파이 차트
        fig_pie = px.pie(df, values='Current Value', names='symbol', title='Asset Allocation')
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # 2. 수익률 바 차트
        fig_bar = px.bar(df, x='symbol', y='Profit %', title='Profit/Loss by Stock',
                         color='Profit %', color_continuous_scale=['red', 'gray', 'green'])
        st.plotly_chart(fig_bar, use_container_width=True)
        
        # 3. 상세 테이블
        st.dataframe(df[['symbol', 'name', 'quantity', 'current_price', 'avg_price', 'Profit %']])
    else:
        st.info("보유 중인 종목이 없습니다.")

    st.divider()

    # 거래 내역 (DB 연동)
    st.subheader("📜 Recent Trade History")
    
    trades = []
    if DB_AVAILABLE:
        try:
            db = get_db()
            # market_code에 맞는 거래 내역 조회
            trades = db.get_trades(market=market_code, limit=20)
        except Exception as e:
            st.warning(f"DB 접근 실패: {e}")
            trades = []
    
    if trades:
        trade_df = pd.DataFrame(trades)
        # 필요한 컬럼만 선택 및 이름 변경
        if not trade_df.empty:
            display_cols = ['timestamp', 'symbol', 'side', 'quantity', 'price', 'amount', 'reason', 'profit_pct']
            # 존재하는 컬럼만 선택
            display_cols = [c for c in display_cols if c in trade_df.columns]
            
            st.dataframe(
                trade_df[display_cols].style.applymap(
                    lambda x: 'color: red' if x == 'SELL' else 'color: green', 
                    subset=['side']
                )
            )
    else:
        if DB_AVAILABLE:
            st.info("최근 거래 내역이 없습니다.")
        else:
            st.warning("데이터베이스 모듈을 로드할 수 없어 거래 내역을 표시할 수 없습니다.")
