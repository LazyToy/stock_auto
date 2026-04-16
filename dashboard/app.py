"""실시간 글로벌 자동 매매 대시보드

AutoTrader가 생성한 상태 파일(JSON)과 로그를 시각화합니다.
실행: streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import json
import os
import time
import sys
import plotly.express as px
from datetime import datetime

# `streamlit run dashboard/app.py`로 직접 실행될 때도
# 프로젝트 루트에서 `dashboard.*`와 `src.*`를 찾을 수 있게 경로를 먼저 보정한다.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.state_loader import load_state as load_state_impl
from dashboard.label_utils import localize_signal_terms, normalize_signal, signal_to_korean
from dashboard.log_utils import resolve_dashboard_log_path
from dashboard.symbol_utils import build_chart_title, build_symbol_label, resolve_company_name
from dashboard.stress_helpers import (
    build_existing_portfolio_weights,
    parse_portfolio_text,
)

# 성장주 탐색기 import
try:
    from src.analysis.growth_stock_finder import GrowthStockFinder
    GROWTH_FINDER_AVAILABLE = True
except ImportError:
    GROWTH_FINDER_AVAILABLE = False

# Database Manager import
try:
    from src.utils.database import get_db, DatabaseManager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# AI Copilot import
try:
    from src.copilot.agent import CopilotAgent
    COPILOT_AVAILABLE = True
    COPILOT_ERR = None
except ImportError as e:
    COPILOT_AVAILABLE = False
    COPILOT_ERR = str(e)

# Multimodal Analyst import
MultimodalAnalyst = None
resolve_price_history = None
try:
    from src.analysis.multimodal import MultimodalAnalyst, resolve_price_history
    MULTIMODAL_AVAILABLE = True
    MULTIMODAL_ERR = None
except ImportError as e:
    MULTIMODAL_AVAILABLE = False
    MULTIMODAL_ERR = str(e)

# AutoML import
try:
    from src.optimization.genetic import GeneticOptimizer
    from src.optimization.automl_support import download_automl_price_history
    AUTOML_AVAILABLE = True
except ImportError:
    AUTOML_AVAILABLE = False

# Stress Test import
try:
    from src.analysis.stress import StressTester
    STRESS_AVAILABLE = True
except ImportError:
    STRESS_AVAILABLE = False

# Debate import
try:
    from src.copilot.debate import DebateManager
    DEBATE_AVAILABLE = True
except ImportError:
    DEBATE_AVAILABLE = False

# 페이지 설정 (와이드 모드, 다크 테마는 Streamlit 설정에서 처리)
st.set_page_config(
    page_title="Global AutoTrading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Components Import
from dashboard.components.overview_tab import render_overview_tab
from dashboard.components.market_tab import render_market_tab
from dashboard.components.growth_tab import render_growth_tab
from dashboard.components.macro_tab import render_macro_tab

# ============================================
# 유틸리티 함수
# ============================================

def load_state(market: str = "KR"):
    """거래 상태 JSON 파일 로드"""
    return load_state_impl(market)


def load_logs(market: str = "KR", lines: int = 50):
    """로그 파일 읽기"""
    log_file = resolve_dashboard_log_path(market)

    if not log_file.exists():
        return []

    try:
        with log_file.open("r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return all_lines[-lines:]
    except Exception as e:
        return [f"[로그 로드 실패] {e}"]


# 사이드바 설정
st.sidebar.title("⚙️ Dashboard Settings")
auto_refresh = st.sidebar.checkbox("Auto Refresh (30s)", value=False)

# 탭 구성 (종합 / KR / US / 성장주 탐색 / AI Copilot / Deep Analysis / AutoML / Stress Test / Agent Debate / Macro)
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "📊 Overview", "🇰🇷 Korean Market", "🇺🇸 US Market",
    "🌱 성장주 탐색", "🤖 AI Copilot", "🧠 심층 분석",
    "🧬 AutoML", "💥 Stress Test", "💬 AI 에이전트 토론", "🌍 Macro 30Y"
])

# 데이터 로드
state_kr = load_state("KR")
state_us = load_state("US")

with tab1:
    render_overview_tab(state_kr, state_us)

with tab2:
    render_market_tab(state_kr, "₩", "KR")

with tab3:
    render_market_tab(state_us, "$", "US")

# ============================================
# 탭 4: 성장 가능성 주 탐색
# ============================================
with tab4:
    render_growth_tab(GROWTH_FINDER_AVAILABLE, GrowthStockFinder if GROWTH_FINDER_AVAILABLE else None)

# ============================================
# 탭 5: AI Copilot
# ============================================
with tab5:
    st.markdown("### 🤖 StockCopilot - AI 트레이딩 비서")

    if not COPILOT_AVAILABLE:
        err_detail = f" (`{COPILOT_ERR}`)" if COPILOT_ERR else ""
        nl = chr(10)
        st.error(
            f"AI Copilot 모듈을 로드할 수 없습니다.{err_detail}"
            + nl + nl
            + "**해결 방법**: 아래 명령어로 필요한 패키지를 설치하세요:"
            + nl + "```" + nl
            + "python -m uv pip install langchain langchain-google-genai google-generativeai"
            + nl + "```"
        )
    else:
        if "copilot_agent" not in st.session_state:
            st.session_state["copilot_agent"] = CopilotAgent()
            st.session_state["messages"] = [
                {"role": "assistant", "content": "안녕하세요! 저는 당신의 투자 비서 StockCopilot입니다. 포트폴리오 상태나 매매 내역에 대해 무엇이든 물어보세요! 😊"}
            ]

        for msg in st.session_state["messages"]:
            st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("질문을 입력하세요 (예: 내 자산 얼마야?, 최근 거래 내역 보여줘)"):
            st.session_state["messages"].append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)

            agent = st.session_state["copilot_agent"]
            with st.spinner("AI가 생각 중입니다..."):
                response_text = agent.process_query(prompt)

            st.session_state["messages"].append({"role": "assistant", "content": response_text})
            st.chat_message("assistant").write(response_text)

# ============================================
# 탭 6: Deep Analysis (Multimodal)
# ============================================
with tab6:
    st.header("🧠 심층 분석")
    st.caption("차트와 뉴스·소셜 데이터를 함께 해석해 종목을 심층 분석합니다. Gemini 기반 멀티모달 분석을 사용합니다.")

    if not MULTIMODAL_AVAILABLE:
        err_detail = f" (`{MULTIMODAL_ERR}`)" if MULTIMODAL_ERR else ""
        nl = chr(10)
        st.error(
            f"심층 분석 모듈을 로드할 수 없습니다.{err_detail}"
            + nl + nl
            + "**해결 방법**: 아래 명령어로 필요한 패키지를 설치하세요:"
            + nl + "```" + nl
            + "python -m uv pip install google-generativeai"
            + nl + "```"
        )
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            ticker_input = st.text_input("분석할 종목 코드", value="AAPL", key="multimodal_ticker")
            analysis_symbol_label = build_symbol_label(ticker_input)
            if analysis_symbol_label:
                st.caption(f"선택 종목: {analysis_symbol_label}")
            analyze_btn = st.button("🚀 심층 분석 시작", type="primary", key="multimodal_btn")

        if analyze_btn:
            assert MultimodalAnalyst is not None
            if "multimodal_analyst" not in st.session_state:
                st.session_state["multimodal_analyst"] = MultimodalAnalyst()
            analyst = st.session_state["multimodal_analyst"]

            with st.spinner(f"{ticker_input} 종목 심층 분석 중... (약 10~20초 소요)"):
                result = analyst.analyze_stock(ticker_input)

            st.divider()

            signal = result.get("signal", "NEUTRAL")
            confidence = float(result.get("confidence", 0.0) or 0.0)
            r_col1, r_col2 = st.columns([1, 1])

            with r_col1:
                st.subheader("차트 분석")
                from src.analysis.chart import ChartGenerator
                from src.analysis.market_data import MarketDataFetcher

                try:
                    assert resolve_price_history is not None
                    chart_fetcher = MarketDataFetcher()
                    _, chart_symbol, chart_df = resolve_price_history(chart_fetcher, ticker_input, period="6mo")
                    if chart_symbol is not None and chart_df is not None and not chart_df.empty:
                        chart_symbol_label = build_symbol_label(chart_symbol or ticker_input)
                        if chart_symbol_label:
                            st.caption(f"차트 기준 종목: {chart_symbol_label}")
                        chart_title = f"{chart_symbol_label} 분석" if chart_symbol_label else f"{ticker_input} 분석"
                        chart_gen = ChartGenerator()
                        chart_buf = chart_gen.generate_chart(chart_df, title=chart_title)
                        if chart_buf is not None:
                            st.image(chart_buf, use_column_width=True)
                        else:
                            st.warning("차트 이미지를 생성하지 못했습니다.")
                    else:
                        st.warning("표시할 차트 데이터가 없습니다.")
                except Exception as e:
                    st.error(f"차트 로드 실패: {e}")

            with r_col2:
                st.subheader("AI 인사이트")
                signal = result.get("signal", "NEUTRAL")
                confidence = result.get("confidence", 0.0)
                reason = localize_signal_terms(result.get("reason", "분석에 실패했습니다."))

                normalized_signal = normalize_signal(signal)
                color = "gray"
                if normalized_signal == "BUY":
                    color = "green"
                elif normalized_signal == "SELL":
                    color = "red"
                elif normalized_signal == "HOLD":
                    color = "orange"

                display_signal = signal_to_korean(signal)
                st.markdown(f"### 신호: :{color}[{display_signal}]")
                st.progress(confidence, text=f"신뢰도: {confidence*100:.0f}%")
                st.markdown("**분석 근거**")
                st.info(reason)

                technical_summary = result.get("technical_summary", "")
                if technical_summary:
                    st.markdown("**기술 지표 요약**")
                    st.text(technical_summary)

                if "raw_text" in result:
                    with st.expander("원본 LLM 응답"):
                        st.text(localize_signal_terms(result["raw_text"]))
# ============================================
# 탭 7: AutoML
# ============================================
with tab7:
    st.header("🧬 AutoML Strategy Evolution")
    if not AUTOML_AVAILABLE:
        st.error("AutoML 최적화 엔진을 불러올 수 없습니다.")
    else:
        st.markdown("### 유전 알고리즘으로 최적 전략 파라미터 탐색")
        st.info("전략 파라미터를 자동으로 진화시켜 최고 성능의 조합을 찾습니다.")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("⚙️ Evolution Settings")
            
            population_size = st.number_input("Population Size", min_value=10, max_value=200, value=50, step=10)
            generations = st.number_input("Generations", min_value=5, max_value=100, value=20, step=5)
            mutation_rate = st.slider("Mutation Rate", 0.0, 1.0, 0.2, 0.05)
            
            st.divider()
            
            strategy_type = st.selectbox("Target Strategy", ["MA Crossover", "RSI", "MACD", "Bollinger Bands"])
            
            test_symbol = st.text_input("Test Symbol", value="005930")
            cleaned_symbol = test_symbol.strip()
            
            if st.button("🚀 Start Evolution", type="primary", key="automl_start"):
                progress_bar = st.progress(0, text="가격 데이터 다운로드 중...")

                try:
                    # 1. 가격 데이터 다운로드
                    st.session_state.pop("automl_result", None)
                    df, resolved_symbol, fetch_error = download_automl_price_history(
                        cleaned_symbol,
                        period="1y",
                        base_dir=os.getcwd(),
                    )
                    # 한국 종목이면 .KS 접미사 추가 (숫자로만 구성된 경우)
                    if fetch_error:
                        st.error(fetch_error)
                        st.stop()

                    if False and df.empty and test_symbol.isdigit():
                        # .KQ로 재시도 (코스닥)
                        yf_symbol = f"{test_symbol}.KQ"
                        ticker_data = yf.Ticker(yf_symbol)
                        df = ticker_data.history(period="1y")

                    if False and df.empty:
                        st.error(
                            f"종목 {test_symbol}의 가격 데이터를 가져올 수 없습니다. "
                            "종목 코드를 확인하세요."
                        )
                        st.stop()

                    progress_bar.progress(0.1, text="가격 데이터 로드 완료. 진화 시작...")

                    # 2. GeneticOptimizer 생성 (항상 새로 생성하여 파라미터 반영)
                    optimizer = GeneticOptimizer(
                        df=df,
                        population_size=population_size,
                        generations=generations,
                        mutation_rate=mutation_rate,
                    )

                    # 3. 진화 실행
                    result_evo = optimizer.evolve(
                        symbol=cleaned_symbol,
                        progress_callback=lambda i, n: progress_bar.progress(
                            min((i + 1) / n, 1.0),
                            text=f"세대 {i + 1}/{n} 진화 중..."
                        )
                    )
                    st.success("✅ Evolution Complete!")
                    if not result_evo.get("history") and result_evo.get("best_params"):
                        result_evo["history"] = [float(result_evo["best_fitness"])]
                    result_evo["resolved_symbol"] = resolved_symbol
                    st.session_state["automl_result"] = result_evo
                except Exception as evo_err:
                    st.session_state.pop("automl_result", None)
                    st.error(f"AutoML 최적화 중 오류가 발생했습니다: {evo_err}")
        
        with col2:
            st.subheader("📊 Evolution Results")
            
            if "automl_result" in st.session_state:
                result = st.session_state["automl_result"]

                st.metric("Best Fitness Score", f"{result['best_fitness']:.4f}")

                st.markdown("**Best Parameters (MACD_RSI):**")
                param_names = ["Fast EMA", "Slow EMA", "Signal", "RSI Window", "RSI Lower", "RSI Upper"]
                if result.get("best_params"):
                    params_display = {
                        name: val
                        for name, val in zip(param_names, result["best_params"])
                    }
                    st.json(params_display)
                else:
                    st.warning("최적 파라미터를 찾지 못했습니다.")

                # Fitness History Chart (history가 있을 때만 표시)
                history = result.get("history", [])
                if history:
                    fitness_df = pd.DataFrame({
                        "Generation": list(range(len(history))),
                        "Fitness": history
                    })
                    fig = px.line(
                        fitness_df, x="Generation", y="Fitness",
                        title="Fitness Evolution",
                        markers=True
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("진화 이력이 없어 차트를 표시할 수 없습니다.")

# ============================================
# 탭 8: Stress Test
# ============================================
with tab8:
    st.header("💥 Portfolio Stress Test")
    if not STRESS_AVAILABLE:
        st.warning("Stress Test 모듈을 로드할 수 없습니다.")
    else:
        st.markdown("### 과거 위기 시나리오에서 포트폴리오 시뮬레이션")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📋 Portfolio Setup")
            
            # 포트폴리오 입력 모드 선택
            mode = st.radio("포트폴리오 입력 방식", 
                           ["수동 입력", "기존 포트폴리오"], 
                           horizontal=True)
            
            if mode == "수동 입력":
                st.caption("종목 코드와 비율을 입력하세요 (미국: AAPL, 한국: 005930.KS)")
                
                # 기본 예시
                default_portfolio = "AAPL:0.3\nMSFT:0.3\nGOOGL:0.4"
                portfolio_text = st.text_area(
                    "종목:비율 (한 줄에 하나씩)", 
                    value=default_portfolio,
                    height=150,
                    help="형식: 종목코드:비율 (예: AAPL:0.5)"
                )
                
                # 파싱
                portfolio_weights = {}
                try:
                    portfolio_weights = parse_portfolio_text(portfolio_text)
                except ValueError:
                    st.error("비율은 숫자로 입력해주세요 (예: 0.5)")
                    portfolio_weights = {}
                
                # 비율 합계 체크
                if portfolio_weights:
                    total_weight = sum(portfolio_weights.values())
                    if abs(total_weight - 1.0) > 0.01:
                        st.warning(f"비율 합계: {total_weight:.2f} (1.0이 권장됩니다)")
            
            else:  # 기존 포트폴리오
                state_data = load_state("KR")
                portfolio_weights = build_existing_portfolio_weights(state_data)
                if not portfolio_weights:
                    st.warning("기존 포트폴리오 데이터가 없습니다. 수동 입력을 사용하세요.")
            
            if portfolio_weights:
                st.dataframe(pd.DataFrame({
                    "Symbol": list(portfolio_weights.keys()),
                    "Weight": [f"{w*100:.1f}%" for w in portfolio_weights.values()]
                }))
                
                total_value = st.number_input("총 포트폴리오 가치", 
                                             min_value=100, 
                                             max_value=1000000000,
                                             value=10000000,
                                             step=1000000,
                                             help="원화 또는 달러 기준")
                
                st.divider()
                
                scenario_name = st.selectbox("위기 시나리오",
                                            ["2008_Financial_Crisis",
                                             "2020_Covid_Crash",
                                             "2022_Inflation_Shock"])
                
                run_test = st.button("🚀 Run Stress Test", type="primary", key="stress_test_run")
            else:
                run_test = False
        
        with col2:
            st.subheader("📊 Simulation Results")
            
            if portfolio_weights and run_test:
                tester = StressTester()
                
                with st.spinner(f"Running {scenario_name} simulation..."):
                    result = tester.simulate_scenario(portfolio_weights, total_value, scenario_name)
                
                if "error" in result:
                    st.error(f"Error: {result['error']}")
                else:
                    portfolio_return = result.get("portfolio_return", 0.0)
                    loss_amount = result.get("total_loss_amount", 0.0)
                    
                    st.metric("Portfolio Return", f"{portfolio_return*100:.2f}%",
                             delta=f"{portfolio_return*100:.2f}%")
                    st.metric("Estimated Loss", f"₩{abs(loss_amount):,.0f}",
                             delta=f"{loss_amount:,.0f}")
                    
                    details = result.get("details", {})
                    if result.get("proxy_used"):
                        st.info("일부 종목은 실데이터 대신 시나리오 프록시 수익률을 사용했습니다.")
                    if details:
                        st.markdown("**종목별 수익률:**")
                        details_df = pd.DataFrame({
                            "Symbol": list(details.keys()),
                            "Return (%)": [f"{v*100:.2f}%" for v in details.values()]
                        })
                        st.dataframe(details_df, use_container_width=True)
                        
                        fig = px.bar(details_df, x="Symbol", y="Return (%)",
                                    title=f"Asset Returns in {scenario_name}")
                        st.plotly_chart(fig, use_container_width=True)
                    
                    if portfolio_return < -0.20:
                        st.error("🔴 **고위험**: 이 시나리오에서 20% 이상 손실!")
                    elif portfolio_return < -0.10:
                        st.warning("🟡 **중위험**: 이 시나리오에서 10~20% 손실.")
                    else:
                        st.success("🟢 **저위험**: 포트폴리오가 비교적 견고합니다.")
            else:
                st.info("포트폴리오를 설정하고 시나리오를 선택한 후 테스트를 실행하세요.")
# ============================================
# 탭 9: Agent Debate
# ============================================
with tab9:
    st.header("💬 AI 에이전트 토론")
    if not DEBATE_AVAILABLE:
        st.warning("토론 모듈을 로드할 수 없습니다.")
    else:
        st.info("기술 분석가, 리스크 관리자, 중재자가 매매 여부를 두고 토론한 뒤 최종 판단을 정리합니다.")

        col1, col2 = st.columns([1, 3])

        with col1:
            # 인기 종목 프리셋
            preset = st.selectbox("종목 프리셋",
                                 ["직접 입력",
                                  "삼성전자 (005930)",
                                  "SK하이닉스 (000660)",
                                  "NVIDIA (NVDA)",
                                  "Apple (AAPL)",
                                  "Tesla (TSLA)"])

            if preset == "직접 입력":
                debate_ticker = st.text_input("종목 코드",
                                             value="AAPL",
                                             help="예: AAPL, TSLA, 317330, 005930",
                                             key="debate_ticker_input")
            else:
                # 프리셋에서 티커 추출 (괄호 안의 값)
                import re
                match = re.search(r"\(([^)]+)\)", preset)
                debate_ticker = match.group(1) if match else "AAPL"

            debate_symbol_label = build_symbol_label(debate_ticker)
            if debate_symbol_label:
                st.info(f"선택된 종목: **{debate_symbol_label}**")

            start_debate = st.button("🚀 토론 시작", type="primary", key="debate_btn")

        with col2:
            if start_debate:
                with st.spinner(f"🗣️ {debate_ticker}에 대한 토론 진행 중... (30초~1분 소요)"):
                    try:
                        dm = DebateManager()
                        consensus = dm.run_debate(debate_ticker)
                    except Exception as e:
                        st.error(f"토론 중 오류가 발생했습니다: {e}")
                        consensus = None

                if consensus:
                    # 최종 판정 표시
                    decision = consensus.get("decision", "HOLD")
                    normalized_decision = normalize_signal(decision)
                    color_map = {"BUY": "green", "SELL": "red", "HOLD": "orange"}
                    display_decision = signal_to_korean(decision)
                    st.markdown(f"### 📊 최종 판정: :{color_map.get(normalized_decision, 'gray')}[{display_decision}]")

                    st.divider()

                    # 토론 내용 표시
                    for entry in consensus.get("history", []):
                        agent_name = entry.get("agent", "Unknown")
                        msg = localize_signal_terms(entry.get("msg", ""))

                        # 에이전트별 아이콘
                        icon_map = {
                            "기술 분석가": "📈",
                            "리스크 관리자": "🛡️",
                            "중재자": "⚖️",
                            "Technical Analyst": "📈",
                            "Risk Manager": "🛡️",
                            "Moderator": "⚖️",
                        }
                        icon = icon_map.get(agent_name, "💬")

                        with st.expander(f"{icon} {agent_name}", expanded=True):
                            st.markdown(msg)
            else:
                st.info("종목을 선택하고 토론을 시작하세요.")

# ============================================
# 탭 10: Macro Investment Dashboard
# ============================================
with tab10:
    st.header("🌍 매크로 투자 대시보드 (30년차 뷰)")
    st.caption("실시간 yfinance 데이터를 기반으로 1분마다 업데이트되며, 매크로 핵심 지표와 30년차 트레이더의 인사이트를 제공합니다.")
    render_macro_tab()

# 자동 새로고침 로직
if auto_refresh:
    time.sleep(30)
    st.rerun()
