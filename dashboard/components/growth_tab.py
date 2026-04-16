import streamlit as st
import pandas as pd
import plotly.express as px
import time

def render_growth_tab(growth_finder_available: bool, growth_finder_class: type = None):
    """성장주 탐색 탭 렌더링"""
    
    st.header("🌱 성장 가능성 주 찾기")
    st.caption("우량주가 아닌 중소형주 중 성장 가능성과 재무 건전성이 좋은 종목 Top 5")
    
    if not growth_finder_available:
        st.error("GrowthStockFinder 모듈을 불러올 수 없습니다.")
        return
    
    # 설정 영역
    col_setting1, col_setting2 = st.columns([1, 2])
    
    with col_setting1:
        # 시장 선택
        market_choice = st.radio("시장 선택", ["🇰🇷 한국", "🇺🇸 미국"], horizontal=True)
        market = "KR" if "한국" in market_choice else "US"
    
    with col_setting2:
        # Tavily API 키 입력 (세션에 저장)
        tavily_key = st.text_input(
            "🔑 Tavily API Key (선택사항)", 
            value=st.session_state.get("tavily_key", ""),
            type="password",
            help="웹 검색 기능 활성화. 없으면 재무 데이터만 분석합니다."
        )
        if tavily_key:
            st.session_state["tavily_key"] = tavily_key
    
    # 분석 모드 표시
    if tavily_key:
        st.success("✅ **하이브리드 모드**: Yahoo Finance + Tavily 웹 검색")
    else:
        st.info("ℹ️ **기본 모드**: Yahoo Finance 재무 데이터만 분석 (Tavily 키 입력 시 웹 검색 추가)")
    
    st.divider()
    
    # 탐색 버튼
    if st.button("🔍 성장 가능성 주 찾기", type="primary", use_container_width=True):
        with st.spinner("실시간 재무 데이터 분석 중..."):
            finder = growth_finder_class(tavily_api_key=tavily_key if tavily_key else None)
            results = finder.search_growth_stocks(market=market)
            
            if results:
                analysis = finder.get_sector_analysis()
                mode_text = "하이브리드" if analysis.get("tavily_enabled") else "재무 데이터"
                st.success(f"✅ Top {len(results)} 성장 가능성 종목 ({mode_text} 분석, 업데이트: {finder.last_update.strftime('%Y-%m-%d %H:%M')})")
                
                # 요약 정보
                col1, col2, col3 = st.columns(3)
                col1.metric("분석 종목 수", f"{analysis['total_stocks']}개")
                col2.metric("평균 성장 점수", f"{analysis['avg_growth_score']:.1f}/10")
                col3.metric("주요 섹터", max(analysis['sectors'], key=analysis['sectors'].get) if analysis['sectors'] else "N/A")
                
                st.divider()
                
                # 카드형 UI로 종목 표시
                st.subheader("📈 추천 종목 Top 5")
                for i, stock in enumerate(results, 1):
                    with st.expander(f"**{i}. {stock.name}** ({stock.symbol}) - {stock.sector}", expanded=(i<=2)):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("성장 점수", f"{stock.growth_score:.1f}/10")
                        c2.metric("재무 건전성", stock.financial_health)
                        c3.metric("매출 성장률", f"{stock.revenue_growth:.1f}%" if stock.revenue_growth else "N/A")
                        c4.metric("영업이익률", f"{stock.profit_margin:.1f}%" if stock.profit_margin else "N/A")
                        
                        # 추가 재무 지표
                        if stock.debt_to_equity or stock.current_ratio or stock.pe_ratio:
                            c5, c6, c7 = st.columns(3)
                            if stock.debt_to_equity:
                                c5.metric("부채비율", f"{stock.debt_to_equity:.1f}%")
                            if stock.current_ratio:
                                c6.metric("유동비율", f"{stock.current_ratio:.2f}")
                            if stock.pe_ratio:
                                c7.metric("PER", f"{stock.pe_ratio:.1f}")
                        
                        st.info(f"💡 **추천 사유**: {stock.reason}")
                        
                        # 뉴스 요약 (Tavily 사용 시)
                        if stock.news_summary:
                            sentiment_color = {"Positive": "🟢", "Negative": "🔴", "Neutral": "⚪"}.get(stock.news_sentiment, "⚪")
                            st.markdown(f"📰 **최신 뉴스** {sentiment_color}: {stock.news_summary}")
                        
                        st.caption(f"시가총액: {stock.market_cap}")
                
                st.divider()
                
                # 상세 테이블
                st.subheader("📊 상세 데이터")
                df = pd.DataFrame(finder.to_dataframe_dict())
                st.dataframe(df, use_container_width=True)
                
                # 성장 점수 차트
                fig = px.bar(
                    df, x='종목명', y='성장점수', 
                    color='섹터', 
                    title='종목별 성장 점수',
                    text='성장점수'
                )
                fig.update_traces(textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.warning("조건에 맞는 종목이 없습니다. 스크리닝 기준을 확인하세요.")
    
    # 안내 메시지
    st.markdown("---")
    st.markdown("""
    ### 📌 분석 방법
    **1단계: Yahoo Finance 재무 스크리닝**
    - 매출 성장률 10% 이상
    - 부채비율 150% 이하
    - 유동비율 1.0 이상
    - 시가총액 $50B 미만 (중소형)
    
    **2단계: Tavily 웹 검색 (API 키 입력 시)**
    - 최신 뉴스 및 트렌드 분석
    - 감성 분석으로 점수 보정
    
    > ⚠️ **주의**: 본 추천은 참고용이며, 투자 조언이 아닙니다.
    """)
