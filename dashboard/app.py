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
from dashboard.streamlit_compat import image_full_width
from dashboard.stress_helpers import (
    STRESS_RESULT_CURRENCY,
    build_existing_portfolio_weights,
    format_display_number,
    format_krw_input_amount,
    format_stress_amount,
    hide_benchmark_traces_by_default,
    infer_symbol_currency,
    load_stress_portfolios,
    normalize_portfolio_weights,
    portfolio_rows_to_weights,
    portfolio_weights_to_rows,
    parse_krw_input_amount,
    save_stress_portfolio,
    split_macro_path_rows,
    validate_portfolio_weights,
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
    from src.optimization.automl_runtime import save_automl_result
    from src.optimization.automl_support import build_fitness_chart_data, download_automl_price_history
    from src.optimization.strategy_registry import strategy_options
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
from dashboard.components.crawling_run_tab import render_crawling_run_tab
from dashboard.components.crawling_results_tab import render_crawling_results_tab
from dashboard.components.smart_money_tab import render_smart_money_tab

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13 = st.tabs([
    "📊 Overview", "🇰🇷 Korean Market", "🇺🇸 US Market",
    "🌱 성장주 탐색", "🤖 AI Copilot", "🧠 심층 분석",
    "🧬 AutoML", "💥 Stress Test", "💬 AI 에이전트 토론", "🌍 Macro 30Y",
    "Smart Money", "크롤링 실행", "크롤링 결과"
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
                            image_full_width(st, chart_buf)
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

                market_context_summary = result.get("market_context_summary", "")
                if market_context_summary:
                    st.markdown("**시장 컨텍스트**")
                    st.text(market_context_summary)

                technical_summary = result.get("technical_summary", "")
                if technical_summary:
                    st.markdown("**기술 지표 요약**")
                    st.text(technical_summary)

                analysis_sources = result.get("analysis_sources", [])
                if analysis_sources:
                    st.markdown("**분석 출처**")
                    st.markdown(", ".join(str(source) for source in analysis_sources))

                key_drivers = result.get("key_drivers", [])
                if key_drivers:
                    st.markdown("**핵심 판단 근거**")
                    for driver in key_drivers:
                        st.markdown(f"- {driver}")

                risk_factors = result.get("risk_factors", [])
                if risk_factors:
                    st.markdown("**리스크 요인**")
                    for risk in risk_factors:
                        st.markdown(f"- {risk}")

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
            
            automl_strategy_options = strategy_options()
            strategy_label = st.selectbox(
                "Target Strategy",
                list(automl_strategy_options.keys()),
            )
            strategy_type = automl_strategy_options[strategy_label]
            fitness_metric = st.selectbox(
                "Fitness Metric",
                ["composite", "sharpe"],
                help="composite는 Sharpe에 초과수익, MDD, turnover penalty를 함께 반영합니다.",
            )
            validation_method = st.selectbox(
                "Validation",
                ["train_test", "walk_forward", "none"],
            )
            if validation_method == "train_test":
                train_ratio = st.slider("Train Ratio", 0.5, 0.9, 0.7, 0.05)
                validation_kwargs = {"train_ratio": train_ratio}
            elif validation_method == "walk_forward":
                train_window = st.number_input("Train Window", min_value=40, max_value=252, value=126, step=21)
                test_window = st.number_input("Test Window", min_value=10, max_value=63, value=21, step=7)
                validation_kwargs = {
                    "train_window": int(train_window),
                    "test_window": int(test_window),
                }
            else:
                validation_kwargs = {}
            
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
                        strategy_type=strategy_type,
                        fitness_metric=fitness_metric,
                    )

                    # 3. 진화 실행
                    result_evo = optimizer.evolve(
                        symbol=cleaned_symbol,
                        validation_method=(None if validation_method == "none" else validation_method),
                        validation_kwargs=validation_kwargs,
                        progress_callback=lambda i, n: progress_bar.progress(
                            min((i + 1) / n, 1.0),
                            text=f"세대 {i + 1}/{n} 진화 중..."
                        )
                    )
                    st.success("✅ Evolution Complete!")
                    if not result_evo.get("history") and result_evo.get("best_params"):
                        result_evo["history"] = [float(result_evo["best_fitness"])]
                    result_evo["resolved_symbol"] = resolved_symbol
                    artifact_path = save_automl_result(result_evo, base_dir=os.getcwd())
                    result_evo["artifact_path"] = str(artifact_path)
                    st.session_state["automl_result"] = result_evo
                except Exception as evo_err:
                    st.session_state.pop("automl_result", None)
                    st.error(f"AutoML 최적화 중 오류가 발생했습니다: {evo_err}")
        
        with col2:
            st.subheader("📊 Evolution Results")
            
            if "automl_result" in st.session_state:
                result = st.session_state["automl_result"]

                st.metric("Best Fitness Score", f"{result['best_fitness']:.4f}")
                st.caption(
                    f"Strategy: {result.get('strategy_display_name', result.get('strategy_type'))} · "
                    f"Fitness: {result.get('fitness_metric', 'sharpe')} · "
                    f"Symbol: {result.get('resolved_symbol') or result.get('symbol')}"
                )

                st.markdown(f"**Best Parameters ({result.get('strategy_type', 'AutoML')}):**")
                param_names = result.get("parameter_labels", [])
                if result.get("best_params"):
                    params_display = {
                        name: val
                        for name, val in zip(param_names, result["best_params"])
                    }
                    st.json(params_display)
                else:
                    st.warning("최적 파라미터를 찾지 못했습니다.")

                validation = result.get("validation")
                if validation:
                    st.markdown("**Validation:**")
                    method = validation.get("method")
                    if method == "train_test":
                        test = validation.get("test", {})
                        metrics = test.get("metrics", {})
                        st.json({
                            "method": method,
                            "test_fitness": test.get("fitness"),
                            "test_sharpe": metrics.get("sharpe"),
                            "test_mdd": metrics.get("max_drawdown"),
                            "fitness_gap": validation.get("fitness_gap"),
                        })
                    elif method == "walk_forward":
                        st.json({
                            "method": method,
                            "fold_count": validation.get("fold_count"),
                            **validation.get("aggregate", {}),
                        })

                if result.get("artifact_path"):
                    st.caption(f"Saved AutoML artifact: {result['artifact_path']}")

                # Fitness History Chart (history가 있을 때만 표시)
                history = result.get("history", [])
                if history:
                    fitness_df = build_fitness_chart_data(history, result.get("validation"))
                    fig = px.line(
                        fitness_df,
                        x="Generation",
                        y="Fitness",
                        color="Series",
                        line_dash="Series",
                        line_dash_map={
                            "Evolution best": "solid",
                            "Validation train": "dot",
                            "Validation test": "dash",
                            "Walk-forward test avg": "dashdot",
                        },
                        title="Fitness Evolution + Validation",
                        markers=True,
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
        scenario_options = (
            StressTester.available_scenarios()
            if hasattr(StressTester, "available_scenarios")
            else StressTester.SCENARIOS
        )

        def format_pct(value):
            if value is None or pd.isna(value):
                return "N/A"
            return f"{value * 100:,.2f}%"
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📋 Portfolio Setup")
            state_data = {}
            portfolio_notice = st.session_state.pop("stress_portfolio_notice", None)
            if portfolio_notice:
                st.success(portfolio_notice)
            
            # 포트폴리오 입력 모드 선택
            mode = st.radio("포트폴리오 입력 방식", 
                           ["수동 입력", "기존 포트폴리오"], 
                           horizontal=True)
            
            if mode == "수동 입력":
                st.caption("표에서 종목과 비중(%)을 바로 수정하세요. 행을 추가해서 종목을 늘릴 수 있습니다.")

                default_portfolio = {"AAPL": 0.3, "MSFT": 0.3, "GOOGL": 0.4}
                if "stress_portfolio_rows" not in st.session_state:
                    st.session_state["stress_portfolio_rows"] = portfolio_weights_to_rows(default_portfolio)
                if "stress_portfolio_editor_revision" not in st.session_state:
                    st.session_state["stress_portfolio_editor_revision"] = 0

                saved_portfolios = load_stress_portfolios()
                if saved_portfolios:
                    load_cols = st.columns([2, 1])
                    saved_names = list(saved_portfolios.keys())
                    selected_saved_portfolio = load_cols[0].selectbox(
                        "저장된 포트폴리오",
                        saved_names,
                        key="stress_saved_portfolio_select",
                    )
                    if load_cols[1].button("불러오기", key="stress_load_saved_portfolio"):
                        st.session_state["stress_portfolio_rows"] = portfolio_weights_to_rows(
                            saved_portfolios[selected_saved_portfolio]
                        )
                        st.session_state["stress_loaded_portfolio_name"] = selected_saved_portfolio
                        st.session_state["stress_save_portfolio_name"] = selected_saved_portfolio
                        st.session_state["stress_portfolio_editor_revision"] += 1
                        st.rerun()
                else:
                    st.caption("저장된 포트폴리오가 아직 없습니다.")

                editor_key = f"stress_portfolio_editor_{st.session_state['stress_portfolio_editor_revision']}"
                edited_portfolio = st.data_editor(
                    pd.DataFrame(st.session_state["stress_portfolio_rows"]),
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Symbol": st.column_config.TextColumn(
                            "Symbol",
                            help="미국: AAPL, 한국: 005930.KS",
                            required=False,
                        ),
                        "Weight (%)": st.column_config.NumberColumn(
                            "Weight (%)",
                            min_value=0.0,
                            max_value=100.0,
                            step=1.0,
                            format="%.2f",
                            help="예: 30은 30% 비중입니다.",
                            required=False,
                        ),
                    },
                    key=editor_key,
                )
                if hasattr(edited_portfolio, "to_dict"):
                    st.session_state["stress_portfolio_rows"] = edited_portfolio.to_dict("records")

                portfolio_weights = {}
                try:
                    portfolio_weights = portfolio_rows_to_weights(edited_portfolio)
                except ValueError:
                    st.error("비중은 숫자로 입력해주세요 (예: 30)")
                    portfolio_weights = {}
                
                # 비율 합계 체크 및 자동 정규화
                if portfolio_weights:
                    validation = validate_portfolio_weights(portfolio_weights)
                    if not validation["is_valid"]:
                        for warning in validation["warnings"]:
                            st.warning(warning)
                        if validation.get("can_normalize"):
                            try:
                                portfolio_weights = normalize_portfolio_weights(portfolio_weights)
                                st.info("비중 합계를 1.00으로 자동 정규화했습니다.")
                            except ValueError:
                                st.error("비중 합계가 0 이하라 스트레스 테스트를 실행할 수 없습니다.")
                                portfolio_weights = {}
                        else:
                            st.error("입력 비중을 정규화할 수 없어 실행을 중단합니다.")
                            portfolio_weights = {}
            
            else:  # 기존 포트폴리오
                state_data = load_state("KR")
                portfolio_weights = build_existing_portfolio_weights(state_data)
                if not portfolio_weights:
                    st.warning("기존 포트폴리오 데이터가 없습니다. 수동 입력을 사용하세요.")
            
            if portfolio_weights:
                save_cols = st.columns([2, 1])
                save_name = save_cols[0].text_input(
                    "포트폴리오 저장 이름",
                    value=st.session_state.get("stress_loaded_portfolio_name", "My Portfolio"),
                    key="stress_save_portfolio_name",
                )
                if save_cols[1].button("저장", key="stress_save_portfolio"):
                    try:
                        saved_name = save_stress_portfolio(save_name, portfolio_weights)
                        st.session_state["stress_loaded_portfolio_name"] = saved_name
                        st.session_state["stress_portfolio_notice"] = f"포트폴리오 저장 완료: {saved_name}"
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

                portfolio_currency = STRESS_RESULT_CURRENCY
                portfolio_currency_label = "KRW"

                try:
                    default_total_value = int(float(state_data.get("total_asset") or 10000000))
                except (TypeError, ValueError):
                    default_total_value = 10000000
                
                total_value_text = st.text_input(
                    "총 포트폴리오 가치",
                    value=format_krw_input_amount(default_total_value),
                    help="원화(KRW) 기준, 예: 10,000,000",
                    key="stress_total_value_krw",
                )
                try:
                    total_value = parse_krw_input_amount(total_value_text)
                    if total_value < 100:
                        raise ValueError("총 포트폴리오 가치는 100원 이상이어야 합니다.")
                except ValueError as exc:
                    st.error(str(exc))
                    total_value = None
                st.caption(
                    "Simulation Results의 포트폴리오 금액/손익/경로는 원화(KRW) 기준입니다. "
                    "종목별 종가/고가/저가는 각 종목의 거래소 quote currency 기준입니다."
                )
                
                st.divider()
                
                scenario_name = st.selectbox("위기 시나리오",
                                            list(scenario_options.keys()),
                                            format_func=lambda key: (
                                                f"{scenario_options[key].name} - "
                                                f"{scenario_options[key].description}"
                                            ))
                
                run_test = st.button(
                    "🚀 Run Stress Test",
                    type="primary",
                    key="stress_test_run",
                    disabled=total_value is None,
                )
            else:
                run_test = False
        
        with col2:
            st.subheader("📊 Simulation Results")
            
            if portfolio_weights and run_test:
                tester = StressTester()
                
                with st.spinner(f"Running {scenario_name} simulation..."):
                    if hasattr(tester, "simulate_named_scenario"):
                        result = tester.simulate_named_scenario(
                            portfolio_weights,
                            total_value,
                            scenario_name,
                        )
                    else:
                        result = tester.simulate_scenario(
                            portfolio_weights,
                            total_value,
                            scenario_name,
                        )
                
                if "error" in result:
                    st.error(f"Error: {result['error']}")
                else:
                    portfolio_return = result.get("portfolio_return", 0.0)
                    loss_amount = result.get("total_loss_amount", 0.0)
                    risk_metrics = result.get("risk_metrics", {})
                    data_quality = result.get("data_quality", {})
                    
                    metric_cols = st.columns(4)
                    metric_cols[0].metric("Portfolio Return", format_pct(portfolio_return),
                                          delta=format_pct(portfolio_return))
                    metric_cols[1].metric(
                        "Estimated P/L",
                        format_stress_amount(loss_amount, portfolio_currency),
                        delta=format_stress_amount(loss_amount, portfolio_currency),
                    )
                    metric_cols[2].metric("Max Drawdown",
                                          format_pct(risk_metrics.get("Max_Drawdown")))
                    metric_cols[3].metric("CVaR 95", format_pct(risk_metrics.get("CVaR_95")))
                    st.caption(
                        f"화폐 표기: 포트폴리오 금액은 {portfolio_currency_label} 기준, "
                        "해외 종목은 시나리오 당시 USD/KRW 환율을 반영합니다. "
                        "종목별 종가/고가/저가 표에는 거래소 quote currency와 원화 환산값을 함께 표시합니다."
                    )
                    st.caption(f"가격 기준: {result.get('price_basis', 'Adjusted OHLC')}")

                    if data_quality:
                        st.caption(
                            "데이터 품질: "
                            f"{data_quality.get('level', 'UNKNOWN')} | "
                            f"실데이터 {format_display_number(data_quality.get('real_data_count', 0), 0)}/"
                            f"{format_display_number(data_quality.get('asset_count', 0), 0)} | "
                            f"프록시 비중 {format_display_number(data_quality.get('proxy_weight', 0.0) * 100, 1)}% | "
                            f"현금 처리 비중 {format_display_number(data_quality.get('excluded_weight', 0.0) * 100, 1)}%"
                        )

                    fx_conversion = result.get("fx_conversion", {})
                    if fx_conversion:
                        if fx_conversion.get("used"):
                            st.info("해외 종목 가격 경로는 시나리오 당시 USD/KRW 환율로 원화 환산했습니다.")
                        elif not fx_conversion.get("available"):
                            st.warning("USD/KRW 환율 데이터를 가져오지 못해 해외 종목은 quote currency 수익률로 계산됐습니다.")
                    
                    details = result.get("details", {})
                    if result.get("proxy_used"):
                        st.info("일부 종목은 실데이터 대신 시나리오 프록시 수익률을 사용했습니다.")
                        for note in result.get("notes", []):
                            st.caption(note)

                    excluded_assets = result.get("excluded_assets", [])
                    if excluded_assets:
                        st.warning("시나리오 당시 상장 전인 종목은 제외하고 해당 비중은 현금(0% 수익률)으로 처리했습니다.")
                        st.dataframe(
                            pd.DataFrame([
                                {
                                    "Symbol": item.get("symbol"),
                                    "Weight (%)": f"{format_display_number(item.get('weight', 0.0) * 100, 2)}%",
                                    "Treatment": item.get("treatment"),
                                    "Reason": item.get("reason"),
                                }
                                for item in excluded_assets
                            ]),
                            use_container_width=True,
                        )

                    proxy_assets = result.get("proxy_assets", [])
                    if proxy_assets:
                        st.markdown("**ETF 프록시 적용 종목:**")
                        st.dataframe(
                            pd.DataFrame([
                                {
                                    "Symbol": item.get("symbol"),
                                    "Proxy ETF": item.get("proxy_symbol"),
                                    "Sector": item.get("sector"),
                                    "Weight (%)": f"{format_display_number(item.get('weight', 0.0) * 100, 2)}%",
                                    "Proxy Return (%)": format_pct(item.get("return")),
                                }
                                for item in proxy_assets
                            ]),
                            use_container_width=True,
                        )

                    macro_summary = result.get("macro_summary", {})
                    macro_items = macro_summary.get("items", []) if macro_summary else []
                    if macro_items:
                        st.markdown("**Macro Summary:**")
                        macro_metric_cols = st.columns(4)
                        for idx, item in enumerate(macro_items[:4]):
                            status = item.get("status")
                            if status == "OK":
                                if item.get("unit") == "yield":
                                    value_text = f"{format_display_number(item.get('display_end', 0), 2)}%"
                                    change_bps = item.get("change_bps")
                                    delta_text = f"{change_bps:+,.0f}bp" if change_bps is not None else "N/A"
                                else:
                                    value_text = format_display_number(item.get("end_value", 0), 2)
                                    delta_text = format_pct(item.get("change_pct"))
                            else:
                                value_text = "데이터 없음"
                                delta_text = None
                            macro_metric_cols[idx].metric(item.get("name", ""), value_text, delta=delta_text)
                        st.dataframe(
                            pd.DataFrame([
                                {
                                    "Name": item.get("name"),
                                    "Symbol": item.get("symbol"),
                                    "Start": format_display_number(
                                        item.get("display_start", item.get("start_value")),
                                        2,
                                    ),
                                    "End": format_display_number(
                                        item.get("display_end", item.get("end_value")),
                                        2,
                                    ),
                                    "Change (%)": format_pct(item.get("change_pct")),
                                    "Change (bp)": format_display_number(item.get("change_bps"), 0),
                                    "Status": item.get("status"),
                                }
                                for item in macro_items
                            ]),
                            use_container_width=True,
                        )

                        usdkrw_rows, other_macro_rows = split_macro_path_rows(result.get("macro_paths", []))
                        usdkrw_macro_df = pd.DataFrame(usdkrw_rows)
                        other_macro_df = pd.DataFrame(other_macro_rows)
                        if not usdkrw_macro_df.empty or not other_macro_df.empty:
                            st.markdown("**Macro Paths:**")
                            st.caption("USD/KRW는 값 범위가 커서 별도 차트로 보고, 나머지 매크로는 시작=100 지수로 추이를 비교합니다.")
                            if not usdkrw_macro_df.empty:
                                fig_usdkrw = px.line(
                                    usdkrw_macro_df,
                                    x="date",
                                    y="value",
                                    color="name",
                                    markers=True,
                                    title=f"USD/KRW Path in {scenario_name}",
                                    labels={
                                        "date": "Date",
                                        "value": "USD/KRW",
                                        "name": "Macro Indicator",
                                    },
                                    hover_data={"value": ":,.2f", "unit": True},
                                )
                                fig_usdkrw.update_yaxes(tickformat=",.2f")
                                st.plotly_chart(fig_usdkrw, use_container_width=True)
                            if not other_macro_df.empty:
                                fig_macro_others = px.line(
                                    other_macro_df,
                                    x="date",
                                    y="indexed_value",
                                    color="name",
                                    markers=True,
                                    title=f"Macro Indicators ex USD/KRW in {scenario_name} (Start = 100)",
                                    labels={
                                        "date": "Date",
                                        "indexed_value": "Index (Start = 100)",
                                        "name": "Macro Indicator",
                                    },
                                    hover_data={
                                        "indexed_value": ":,.2f",
                                        "value": ":,.2f",
                                        "unit": True,
                                    },
                                )
                                fig_macro_others.update_yaxes(tickformat=",.2f")
                                st.plotly_chart(fig_macro_others, use_container_width=True)

                    portfolio_extremes = result.get("portfolio_extremes", {})
                    if portfolio_extremes:
                        extreme_cols = st.columns(2)
                        extreme_cols[0].metric(
                            "Scenario High",
                            format_stress_amount(
                                portfolio_extremes.get('highest_value', 0),
                                portfolio_currency,
                            ),
                            delta=format_pct(portfolio_extremes.get("highest_return")),
                        )
                        extreme_cols[0].caption(
                            f"최고 시점: {portfolio_extremes.get('highest_date', 'N/A')}"
                        )
                        extreme_cols[1].metric(
                            "Scenario Low",
                            format_stress_amount(
                                portfolio_extremes.get('lowest_value', 0),
                                portfolio_currency,
                            ),
                            delta=format_pct(portfolio_extremes.get("lowest_return")),
                        )
                        extreme_cols[1].caption(
                            f"최저 시점: {portfolio_extremes.get('lowest_date', 'N/A')}"
                        )

                    benchmark_rows = result.get("benchmark_comparison", [])
                    if benchmark_rows:
                        st.markdown("**Benchmark Comparison:**")
                        st.dataframe(
                            pd.DataFrame([
                                {
                                    "Benchmark": row.get("name"),
                                    "Symbol": row.get("symbol"),
                                    "Return (%)": format_pct(row.get("return")),
                                    "Ending Value (KRW)": (
                                        format_stress_amount(row.get("ending_value"), portfolio_currency)
                                        if row.get("ending_value") is not None
                                        else "N/A"
                                    ),
                                    "Status": row.get("status"),
                                }
                                for row in benchmark_rows
                            ]),
                            use_container_width=True,
                        )

                    path_df = pd.DataFrame(result.get("path", []))
                    if not path_df.empty:
                        st.markdown("**포트폴리오 경로:**")
                        st.caption(
                            f"포트폴리오 가치 축은 {portfolio_currency_label} 기준입니다. "
                            "해외 종목은 USD/KRW 환율 경로를 반영합니다."
                        )
                        fig_path = px.line(
                            path_df,
                            x="date",
                            y="portfolio_value",
                            title=f"Portfolio Equity Path in {scenario_name}",
                            labels={
                                "date": "Date",
                                "portfolio_value": f"Portfolio Value ({portfolio_currency_label})",
                            },
                            hover_data={"portfolio_value": ":,.0f", "portfolio_return": ":,.2%"},
                        )
                        fig_path.update_yaxes(tickformat=",.0f")
                        st.plotly_chart(fig_path, use_container_width=True)

                    asset_path_df = pd.DataFrame(result.get("asset_price_paths", []))
                    benchmark_path_df = pd.DataFrame(result.get("benchmark_price_paths", []))
                    if not asset_path_df.empty:
                        asset_path_df["series_type"] = "Holding"
                        asset_path_df["display_label"] = "Holding: " + asset_path_df["symbol"].astype(str)
                    if not benchmark_path_df.empty:
                        benchmark_path_df["series_type"] = "Benchmark"
                        benchmark_path_df["display_label"] = (
                            "Benchmark: "
                            + benchmark_path_df["symbol"].astype(str)
                            + " ("
                            + benchmark_path_df.get("name", benchmark_path_df["symbol"]).astype(str)
                            + ")"
                        )
                    price_path_df = pd.concat(
                        [df for df in [asset_path_df, benchmark_path_df] if not df.empty],
                        ignore_index=True,
                    ) if (not asset_path_df.empty or not benchmark_path_df.empty) else pd.DataFrame()
                    if not price_path_df.empty:
                        st.markdown("**종목별 가격 경로:**")
                        st.caption(
                            "종가: 각 종목 거래소의 quote currency 가격입니다. "
                            "원화 환산: 해외 종목은 당시 USD/KRW 환율을 곱한 값입니다. "
                            "진입가=100: 원화 환산 진입가를 100으로 둔 비교 지수입니다. "
                            "Benchmark 라벨은 같은 기간 주요 ETF 벤치마크입니다."
                        )
                        price_tab, krw_tab, indexed_tab = st.tabs(["종가", "원화 환산", "진입가 = 100"])
                        with price_tab:
                            fig_asset_price = px.line(
                                price_path_df,
                                x="date",
                                y="close",
                                color="display_label",
                                line_dash="series_type",
                                markers=True,
                                title=f"Asset Close Prices in {scenario_name}",
                                labels={
                                    "date": "Date",
                                    "close": "Close Price (Quote Currency)",
                                    "display_label": "Series",
                                    "series_type": "Type",
                                },
                                hover_data={"close": ":,.2f", "quote_currency": True},
                            )
                            fig_asset_price.update_yaxes(tickformat=",.2f")
                            hide_benchmark_traces_by_default(fig_asset_price)
                            st.plotly_chart(fig_asset_price, use_container_width=True)
                        with krw_tab:
                            fig_asset_price_krw = px.line(
                                price_path_df,
                                x="date",
                                y="close_krw",
                                color="display_label",
                                line_dash="series_type",
                                markers=True,
                                title=f"Asset KRW-Converted Prices in {scenario_name}",
                                labels={
                                    "date": "Date",
                                    "close_krw": "KRW-Converted Price",
                                    "display_label": "Series",
                                    "series_type": "Type",
                                },
                                hover_data={"close_krw": ":,.0f"},
                            )
                            fig_asset_price_krw.update_yaxes(tickformat=",.0f")
                            hide_benchmark_traces_by_default(fig_asset_price_krw)
                            st.plotly_chart(fig_asset_price_krw, use_container_width=True)
                        with indexed_tab:
                            fig_asset_indexed = px.line(
                                price_path_df,
                                x="date",
                                y="indexed_price",
                                color="display_label",
                                line_dash="series_type",
                                markers=True,
                                title=f"Asset Price Index in {scenario_name} (Entry = 100)",
                                labels={
                                    "date": "Date",
                                    "indexed_price": "Price Index (Entry = 100)",
                                    "display_label": "Series",
                                    "series_type": "Type",
                                },
                                hover_data={"indexed_price": ":,.2f"},
                            )
                            fig_asset_indexed.update_yaxes(tickformat=",.2f")
                            hide_benchmark_traces_by_default(fig_asset_indexed)
                            st.plotly_chart(fig_asset_indexed, use_container_width=True)

                    asset_extremes = result.get("asset_extremes", {})
                    if asset_extremes:
                        st.markdown("**종목별 진입가 및 시나리오 고가/저가:**")
                        extremes_df = pd.DataFrame([
                            {
                                "Symbol": symbol,
                                "Quote Currency": values.get("quote_currency", infer_symbol_currency(symbol)),
                                "Proxy ETF": values.get("proxy_symbol"),
                                "Entry Date": values.get("entry_date"),
                                "Entry Close (Quote)": format_display_number(values.get("entry_close"), 2),
                                "Exit Close (Quote)": format_display_number(values.get("exit_close"), 2),
                                "Scenario High (Quote)": format_display_number(values.get("scenario_high"), 2),
                                "Entry Close (KRW)": format_display_number(values.get("entry_close_krw"), 0),
                                "Exit Close (KRW)": format_display_number(values.get("exit_close_krw"), 0),
                                "Scenario High (KRW)": format_display_number(values.get("scenario_high_krw"), 0),
                                "High Return (%)": format_pct(values.get("scenario_high_return")),
                                "Scenario Low (Quote)": format_display_number(values.get("scenario_low"), 2),
                                "Scenario Low (KRW)": format_display_number(values.get("scenario_low_krw"), 0),
                                "Low Return (%)": format_pct(values.get("scenario_low_return")),
                                "Note": values.get("entry_note", ""),
                            }
                            for symbol, values in asset_extremes.items()
                        ])
                        st.dataframe(extremes_df, use_container_width=True)

                    if details:
                        st.markdown("**종목별 수익률:**")
                        details_chart_df = pd.DataFrame({
                            "Symbol": list(details.keys()),
                            "Return (%)": [v * 100 for v in details.values()],
                        })
                        details_table_df = pd.DataFrame({
                            "Symbol": list(details.keys()),
                            "Return (%)": [format_pct(v) for v in details.values()],
                        })
                        st.dataframe(details_table_df, use_container_width=True)
                        
                        fig = px.bar(
                            details_chart_df,
                            x="Symbol",
                            y="Return (%)",
                            title=f"Asset Returns in {scenario_name}",
                            hover_data={"Return (%)": ":,.2f"},
                        )
                        fig.update_yaxes(tickformat=",.2f")
                        st.plotly_chart(fig, use_container_width=True)

                    risk_level = result.get("risk_classification", "LOW")
                    if risk_level == "DATA_LIMITED":
                        st.warning("데이터 부족: 프록시 비중이 높아 위험 등급을 보류합니다.")
                    elif risk_level == "HIGH_DATA_LIMITED":
                        st.error("🔴 **고위험/데이터 제한**: 큰 손실 신호가 있으나 프록시 비중도 높습니다.")
                    elif risk_level == "MEDIUM_DATA_LIMITED":
                        st.warning("🟡 **중위험/데이터 제한**: 손실 신호가 있으나 프록시 비중도 높습니다.")
                    elif risk_level == "HIGH":
                        st.error("🔴 **고위험**: 이 시나리오에서 20% 이상 손실 또는 경로 낙폭이 관측됩니다.")
                    elif risk_level == "MEDIUM":
                        st.warning("🟡 **중위험**: 이 시나리오에서 10~20% 수준의 손실 위험이 있습니다.")
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

with tab11:
    render_smart_money_tab()

with tab12:
    render_crawling_run_tab()

with tab13:
    render_crawling_results_tab()

# 자동 새로고침 로직
if auto_refresh:
    time.sleep(30)
    st.rerun()
