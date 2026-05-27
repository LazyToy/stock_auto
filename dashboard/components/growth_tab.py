import streamlit as st
import pandas as pd
import plotly.express as px
import inspect
import math
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from src.analysis.growth_validation import (
    GrowthCandidateSnapshot,
    GrowthValidationResult,
    load_growth_candidate_snapshots,
    save_growth_candidate_snapshots,
    snapshots_from_growth_stocks,
    summarize_validation,
    validate_growth_candidates,
)


TERM_EXPLANATIONS = {
    "현재가": "현재 화면에 표시된 종목 가격입니다. 한국 종목은 KRW, 미국 종목은 USD 기준으로 표시합니다.",
    "성장 점수": "재무 성장성, 시장 관심도, 수급, 밸류에이션, 리스크 감점을 합산한 1~10점 후보 평가 점수입니다.",
    "재무 건전성": "부채비율, 유동비율, 이익률을 바탕으로 Excellent/Good/Fair/Poor로 구분한 재무 안정성 등급입니다.",
    "매출 성장률": "최근 매출이 전년 또는 직전 기간 대비 얼마나 증가했는지 보는 성장성 지표입니다.",
    "영업이익률": "매출에서 영업이익이 차지하는 비율입니다. 성장의 질과 수익성을 함께 확인합니다.",
    "시장 관심도": "거래대금, 누적 모멘텀, 거래량 증가, 고점 근접도를 조합한 시장 관심 점수입니다.",
    "20일 모멘텀": "최근 20영업일 동안 가격이 얼마나 상승 또는 하락했는지 보는 추세 지표입니다.",
    "거래량 비율": "최근 5일 평균 거래량을 이전 20일 평균 거래량과 비교한 값입니다. 1보다 크면 거래 관심이 증가한 상태입니다.",
    "데이터 신뢰도": "재무 지표 5개 중 실제로 확보된 지표 비율입니다. 낮으면 점수에 보수적 감점이 들어갑니다.",
    "수급 점수": "외국인과 기관의 최근 순매수, 5일 누적, 매수전환/매도전환을 -0.5~+1.0 범위로 점수화한 값입니다.",
    "5일 스마트머니": "최근 5거래일 외국인 순매수와 기관 순매수를 합산한 값입니다. 네이버 데이터는 주식 수(주), pykrx fallback은 거래대금(KRW) 기준입니다.",
    "최근 1일 외국인": "가장 최근 거래일의 외국인 순매수 값입니다. 음수면 외국인 순매도입니다. 단위는 라벨과 값에 함께 표시합니다.",
    "최근 1일 기관": "가장 최근 거래일의 기관 순매수 값입니다. 음수면 기관 순매도입니다. 단위는 라벨과 값에 함께 표시합니다.",
    "재무 성장성": "매출 성장률에서 얻은 점수입니다. 성장 속도가 빠를수록 높아집니다.",
    "수익성/건전성": "이익률, 부채비율, 유동비율에서 얻은 점수입니다. 수익성과 재무 안정성을 함께 봅니다.",
    "3년 지속성": "최근 수년간 매출 CAGR과 영업이익 개선 흐름을 평가한 장기 성장 지속성 점수입니다.",
    "밸류에이션": "PER가 과도하게 높거나 낮은지 참고해 반영하는 보조 점수입니다.",
    "리스크 감점": "재무 데이터 부족, 과열, 불확실성 등으로 최종 점수에서 차감되는 항목입니다.",
    "3년 매출 CAGR": "최근 3년 내 매출의 연평균 성장률입니다. 단발 성장이 아니라 지속성을 확인합니다.",
    "섹터 순위": "같은 섹터 후보들 중 시장 관심도 기준 몇 번째인지 보여줍니다.",
    "섹터 백분위": "같은 섹터 안에서 상대적으로 어느 정도 상위권인지 0~100%로 나타낸 값입니다.",
    "부채비율": "자기자본 대비 부채 규모입니다. 낮을수록 재무 부담이 작습니다.",
    "유동비율": "단기 자산이 단기 부채를 얼마나 커버하는지 보는 안정성 지표입니다.",
    "PER": "주가를 주당순이익으로 나눈 값입니다. 시장이 이익 대비 얼마를 지불하는지 보여주는 밸류에이션 지표입니다.",
}


def build_growth_backtest_command(
    *,
    start: date,
    end: date,
    horizons: str = "1,3,5",
    surge_threshold: int = 15,
) -> str:
    """조기신호 백테스트 CLI 명령을 생성한다."""
    return (
        "python -m src.crawling.backtest_early_signal "
        f"--start {start.isoformat()} --end {end.isoformat()} "
        f"--horizons {horizons} --surge-threshold {surge_threshold}"
    )


def build_growth_backtest_args(
    *,
    start: date,
    end: date,
    horizons: str = "1,3,5",
    surge_threshold: int = 15,
) -> list[str]:
    """현재 Streamlit과 같은 Python으로 조기신호 백테스트를 실행할 인자를 만든다."""
    return [
        sys.executable,
        "-m",
        "src.crawling.backtest_early_signal",
        "--start",
        start.isoformat(),
        "--end",
        end.isoformat(),
        "--horizons",
        horizons,
        "--surge-threshold",
        str(surge_threshold),
    ]


def run_growth_backtest(
    *,
    start: date,
    end: date,
    horizons: str = "1,3,5",
    surge_threshold: int = 15,
    timeout_seconds: int = 600,
    runner=None,
):
    """웹 버튼에서 조기신호 백테스트 CLI를 안전하게 실행한다."""
    run = runner or subprocess.run
    return run(
        build_growth_backtest_args(
            start=start,
            end=end,
            horizons=horizons,
            surge_threshold=surge_threshold,
        ),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def find_latest_backtest_report(reports_dir: str | Path = "reports") -> Path | None:
    """reports 디렉터리에서 최신 조기신호 백테스트 리포트를 찾는다."""
    base = Path(reports_dir)
    if not base.exists():
        return None
    reports = sorted(base.glob("backtest_*.md"), key=lambda path: path.name, reverse=True)
    return reports[0] if reports else None


def read_backtest_report_preview(path: str | Path, *, max_chars: int = 4000) -> str:
    """Markdown 리포트 preview 문자열을 반환한다."""
    text = Path(path).read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def list_growth_candidate_snapshot_files(
    candidates_dir: str | Path = "data/growth_candidates",
) -> list[Path]:
    """저장된 성장 후보 스냅샷 파일을 최신 날짜순으로 찾는다."""
    base = Path(candidates_dir)
    if not base.exists():
        return []
    return sorted(base.glob("growth_candidates_*.csv"), key=lambda path: path.name, reverse=True)


def search_growth_stocks_compat(
    finder,
    *,
    market: str,
    candidate_mode: str,
    candidate_limit: int,
    prefilter_limit: int,
    interest_window_days: int,
):
    """Streamlit hot-reload 중 예전 finder 인스턴스가 남아도 안전하게 호출한다."""
    kwargs = {
        "market": market,
        "candidate_mode": candidate_mode,
        "candidate_limit": candidate_limit,
        "prefilter_limit": prefilter_limit,
    }
    try:
        signature = inspect.signature(finder.search_growth_stocks)
        accepts_window = (
            "interest_window_days" in signature.parameters
            or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        )
    except (TypeError, ValueError):
        accepts_window = True

    if accepts_window:
        kwargs["interest_window_days"] = interest_window_days
    return finder.search_growth_stocks(**kwargs)


def format_optional_number(value, *, suffix: str = "", digits: int = 1) -> str:
    """숫자가 없거나 오래된 객체 필드가 비어 있으면 N/A로 표시한다."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(number):
        return "N/A"
    return f"{number:,.{digits}f}{suffix}"


def format_currency_price(value, currency: str = "") -> str:
    """가격을 통화와 천단위 콤마가 포함된 문자열로 표시한다."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(number):
        return "N/A"
    currency = str(currency or "").upper()
    if currency in {"KRW", "JPY"}:
        return f"{number:,.0f} {currency}"
    if currency:
        return f"{number:,.2f} {currency}"
    return f"{number:,.2f}"


def format_supply_flow_value(value, unit: str = "") -> str:
    """수급 값을 데이터 출처 단위와 함께 표시한다."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(number):
        return "N/A"
    unit = str(unit or "").strip()
    if unit.upper() in {"KRW", "USD"}:
        return format_currency_price(number, unit)
    if unit:
        return f"{number:,.0f} {unit}"
    return f"{number:,.0f}"


def normalize_supply_flow_unit(unit: str = "", source: str = "") -> str:
    """수급 출처 기준으로 화면에 표시할 단위를 결정한다."""
    normalized = str(unit or "").strip()
    if normalized:
        return normalized.upper() if normalized.upper() in {"KRW", "USD"} else normalized
    source = str(source or "").lower()
    if source == "naver":
        return "주"
    if source == "pykrx":
        return "KRW"
    return ""


def format_supply_flow_label(label: str, unit: str = "", *, source: str = "") -> str:
    """수급 지표 라벨에 단위를 직접 붙여 화면에서 놓치지 않게 한다."""
    display_unit = normalize_supply_flow_unit(unit, source)
    return f"{label}({display_unit})" if display_unit else label


def format_optional_percent(value, *, digits: int = 0) -> str:
    """0~1 비율 값을 퍼센트로 표시한다."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(number):
        return "N/A"
    return f"{number:.{digits}%}"


def render_metric_with_help(label: str, value, *, explanation_key: str | None = None, **metric_kwargs) -> None:
    """Metric 라벨 옆에 Streamlit 기본 도움말 아이콘을 붙인다."""
    explanation = TERM_EXPLANATIONS.get(explanation_key or label)
    st.metric(label, value, help=explanation, **metric_kwargs)


def fetch_growth_validation_price_history(
    snapshots: list[GrowthCandidateSnapshot],
    *,
    history_fetcher=None,
) -> dict[str, pd.DataFrame]:
    """저장 후보의 20일/60일 검증에 필요한 가격 이력을 조회한다.

    국내 6자리 종목코드는 yfinance에서 KOSDAQ(.KQ), KOSPI(.KS)를 순서대로 시도하고,
    검증 결과는 저장 CSV의 원래 symbol 키로 매핑한다.
    """
    if not snapshots:
        return {}

    fetcher = history_fetcher or _fetch_yfinance_history
    start, end = _growth_validation_history_window(snapshots)
    histories: dict[str, pd.DataFrame] = {}
    seen_symbols = []
    for snapshot in snapshots:
        if snapshot.symbol not in seen_symbols:
            seen_symbols.append(snapshot.symbol)

    for original_symbol in seen_symbols:
        histories[original_symbol] = pd.DataFrame()
        for lookup_symbol in _growth_validation_symbol_variants(original_symbol):
            history = fetcher(lookup_symbol, start=start, end=end)
            if _has_close_history(history):
                histories[original_symbol] = history
                break

    return histories


def growth_validation_results_to_dataframe(
    results: list[GrowthValidationResult],
) -> pd.DataFrame:
    """성장 후보 사후검증 결과를 화면 표시용 DataFrame으로 변환한다."""
    rows = []
    for result in results:
        rows.append(
            {
                "날짜": result.date.strftime("%Y-%m-%d"),
                "종목코드": result.symbol,
                "종목명": result.name,
                "섹터": result.sector or "",
                "점수": round(result.score, 2),
                "20일수익률(%)": _round_optional(result.return_20d),
                "20일Hit": result.hit_20d,
                "60일수익률(%)": _round_optional(result.return_60d),
                "60일Hit": result.hit_60d,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "날짜",
            "종목코드",
            "종목명",
            "섹터",
            "점수",
            "20일수익률(%)",
            "20일Hit",
            "60일수익률(%)",
            "60일Hit",
        ],
    )


def _growth_validation_symbol_variants(symbol: str) -> list[str]:
    normalized = str(symbol).strip()
    if normalized.isdigit() and len(normalized) == 6:
        return [f"{normalized}.KQ", f"{normalized}.KS", normalized]
    return [normalized]


def _growth_validation_history_window(
    snapshots: list[GrowthCandidateSnapshot],
) -> tuple[date, date]:
    snapshot_dates = [pd.Timestamp(snapshot.date).date() for snapshot in snapshots]
    start = min(snapshot_dates) - timedelta(days=10)
    end = max(max(snapshot_dates) + timedelta(days=120), date.today() + timedelta(days=1))
    return start, end


def _fetch_yfinance_history(symbol: str, *, start: date, end: date) -> pd.DataFrame:
    yf = __import__("yfinance")
    return yf.Ticker(symbol).history(
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False,
    )


def _has_close_history(history) -> bool:
    if history is None or not isinstance(history, pd.DataFrame):
        return False
    if history.empty or "Close" not in history.columns:
        return False
    return not pd.to_numeric(history["Close"], errors="coerce").dropna().empty


def _round_optional(value):
    return None if value is None else round(float(value), 2)


def _format_sector_rank(stock) -> str:
    rank = getattr(stock, "sector_rank", None)
    count = getattr(stock, "sector_count", 0)
    if rank is None or not count:
        return "N/A"
    return f"{rank}/{count}"


def save_growth_results_for_validation(
    results: list[object],
    *,
    snapshot_date: date,
    output_dir: str | Path = "data/growth_candidates",
) -> Path:
    """현재 성장 후보 검색 결과를 사후검증용 CSV 스냅샷으로 저장한다."""
    snapshots = snapshots_from_growth_stocks(results, snapshot_date=snapshot_date)
    return save_growth_candidate_snapshots(snapshots, output_dir=output_dir)


def render_growth_tab(growth_finder_available: bool, growth_finder_class: type = None):
    """성장주 탐색 탭 렌더링"""
    
    st.header("🌱 성장 가능성 주 찾기")
    st.caption("실시간 시장 스캔으로 최근 며칠~몇 주간 관심이 붙은 종목을 먼저 찾고, 상위 후보만 재무제표로 검증합니다.")
    
    if not growth_finder_available:
        st.error("GrowthStockFinder 모듈을 불러올 수 없습니다.")
        return
    
    # 설정 영역
    col_setting1, col_setting2, col_setting3 = st.columns([1, 1.4, 2])
    
    with col_setting1:
        # 시장 선택
        market_choice = st.radio("시장 선택", ["🇰🇷 한국", "🇺🇸 미국"], horizontal=True)
        market = "KR" if "한국" in market_choice else "US"

        candidate_mode_label = st.selectbox(
            "후보 생성",
            ["실시간 시장 스캔", "고정 후보군"],
            help="실시간 시장 스캔은 전체 시장에서 시장 관심도 상위 후보를 만든 뒤 재무제표를 확인합니다.",
        )
        candidate_mode = "market" if candidate_mode_label.startswith("실시간") else "static"
    
    with col_setting2:
        candidate_limit = st.slider(
            "재무 확인 후보 수",
            min_value=10,
            max_value=120,
            value=60,
            step=10,
            disabled=(candidate_mode == "static"),
            help="시장 관심도 상위 몇 종목까지 yfinance 재무 스크리닝을 돌릴지 정합니다.",
        )
        prefilter_limit = st.slider(
            "일봉 확인 후보 수",
            min_value=50,
            max_value=400,
            value=200,
            step=50,
            disabled=(candidate_mode == "static"),
            help="유동성/당일 관심도로 먼저 압축한 뒤 이 후보들만 6개월 일봉을 조회합니다.",
        )
        interest_window_days = st.radio(
            "관심 누적 기간",
            options=[20, 60],
            format_func=lambda value: f"최근 {value}일",
            horizontal=True,
            disabled=(candidate_mode == "static"),
            help="단발 급등보다 며칠~몇 주간 누적된 관심을 볼 기간입니다.",
        )

    with col_setting3:
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
    if candidate_mode == "market" and tavily_key:
        st.success("✅ **실시간 시장 스캔 + 재무제표 + Tavily 웹 검색**")
    elif candidate_mode == "market":
        st.info("ℹ️ **실시간 시장 스캔 + 재무제표**: 시장 관심도 상위 후보만 재무 데이터로 검증합니다.")
    elif tavily_key:
        st.success("✅ **고정 후보군 + Tavily 웹 검색**")
    else:
        st.info("ℹ️ **고정 후보군**: 기존 후보 리스트만 재무 데이터로 분석합니다.")
    
    st.divider()
    
    # 탐색 버튼
    if st.button("🔍 성장 가능성 주 찾기", type="primary", use_container_width=True):
        spinner_text = "실시간 시장 스캔 및 재무 데이터 분석 중..." if candidate_mode == "market" else "재무 데이터 분석 중..."
        with st.spinner(spinner_text):
            finder = growth_finder_class(tavily_api_key=tavily_key if tavily_key else None)
            results = search_growth_stocks_compat(
                finder,
                market=market,
                candidate_mode=candidate_mode,
                candidate_limit=candidate_limit,
                prefilter_limit=prefilter_limit,
                interest_window_days=int(interest_window_days or 20),
            )
            
            if results:
                st.session_state["growth_last_results"] = results
                st.session_state["growth_last_market"] = market
                st.session_state["growth_last_saved_at"] = date.today()
                analysis = finder.get_sector_analysis()
                mode_text = "하이브리드" if analysis.get("tavily_enabled") else "재무 데이터"
                st.success(f"✅ Top {len(results)} 성장 가능성 종목 ({mode_text} 분석, 업데이트: {finder.last_update.strftime('%Y-%m-%d %H:%M')})")
                
                # 요약 정보
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("분석 종목 수", f"{analysis['total_stocks']}개")
                col2.metric("평균 성장 점수", f"{analysis['avg_growth_score']:.1f}/10")
                col3.metric("주요 섹터", max(analysis['sectors'], key=analysis['sectors'].get) if analysis['sectors'] else "N/A")
                if analysis.get("candidate_source") == "market":
                    col4.metric("시장 후보", f"{analysis.get('market_candidate_count', 0)}개")
                else:
                    col4.metric("후보 소스", "고정")
                
                st.divider()
                
                # 카드형 UI로 종목 표시
                st.subheader("📈 검토 후보 Top 5")
                for i, stock in enumerate(results, 1):
                    with st.expander(f"**{i}. {stock.name}** ({stock.symbol}) - {stock.sector}", expanded=(i<=2)):
                        c0, c1, c2, c3, c4 = st.columns(5)
                        with c0:
                            render_metric_with_help(
                                "현재가",
                                format_currency_price(
                                    getattr(stock, "current_price", None),
                                    getattr(stock, "price_currency", ""),
                                ),
                            )
                        with c1:
                            render_metric_with_help("성장 점수", f"{stock.growth_score:.1f}/10")
                        with c2:
                            render_metric_with_help("재무 건전성", stock.financial_health)
                        with c3:
                            render_metric_with_help(
                                "매출 성장률",
                                f"{stock.revenue_growth:.1f}%" if stock.revenue_growth else "N/A",
                            )
                        with c4:
                            render_metric_with_help(
                                "영업이익률",
                                f"{stock.profit_margin:.1f}%" if stock.profit_margin else "N/A",
                            )

                        market_interest_score = getattr(stock, "market_interest_score", None)
                        if market_interest_score is not None:
                            m1, m2, m3, m4 = st.columns(4)
                            with m1:
                                render_metric_with_help("시장 관심도", format_optional_number(market_interest_score))
                            with m2:
                                render_metric_with_help(
                                    "20일 모멘텀",
                                    format_optional_number(getattr(stock, "momentum_20d", None), suffix="%"),
                                )
                            with m3:
                                render_metric_with_help(
                                    "거래량 비율",
                                    format_optional_number(getattr(stock, "volume_ratio_20d", None), suffix="x"),
                                )
                            with m4:
                                render_metric_with_help(
                                    "데이터 신뢰도",
                                    format_optional_percent(getattr(stock, "data_confidence", None)),
                                )

                        supply_flow_score = getattr(stock, "supply_flow_score", None)
                        if supply_flow_score is not None:
                            flow_source = getattr(stock, "supply_flow_source", "")
                            supply_flow_unit = normalize_supply_flow_unit(
                                getattr(stock, "supply_flow_unit", ""),
                                flow_source,
                            )
                            f1, f2, f3, f4 = st.columns(4)
                            with f1:
                                render_metric_with_help("수급 점수", format_optional_number(supply_flow_score))
                            with f2:
                                render_metric_with_help(
                                    format_supply_flow_label("5일 스마트머니", supply_flow_unit),
                                    format_supply_flow_value(
                                        getattr(stock, "smart_money_5d_sum", None),
                                        supply_flow_unit,
                                    ),
                                    explanation_key="5일 스마트머니",
                                )
                            with f3:
                                render_metric_with_help(
                                    format_supply_flow_label("최근 1일 외국인", supply_flow_unit),
                                    format_supply_flow_value(
                                        getattr(stock, "latest_foreign_flow", None),
                                        supply_flow_unit,
                                    ),
                                    explanation_key="최근 1일 외국인",
                                )
                            with f4:
                                render_metric_with_help(
                                    format_supply_flow_label("최근 1일 기관", supply_flow_unit),
                                    format_supply_flow_value(
                                        getattr(stock, "latest_institution_flow", None),
                                        supply_flow_unit,
                                    ),
                                    explanation_key="최근 1일 기관",
                                )
                            flow_reversal = getattr(stock, "supply_flow_reversal", "")
                            source_text = f"source={flow_source}" if flow_source else "source=N/A"
                            unit_text = f"unit={supply_flow_unit}" if supply_flow_unit else "unit=N/A"
                            reversal_text = f" · 수급 전환: {flow_reversal}" if flow_reversal else ""
                            st.caption(f"수급 데이터: {source_text}, {unit_text}{reversal_text}")

                        with st.expander("점수 구성", expanded=False):
                            s1, s2, s3, s4, s5 = st.columns(5)
                            with s1:
                                render_metric_with_help(
                                    "재무 성장성",
                                    format_optional_number(getattr(stock, "financial_growth_score", None)),
                                )
                            with s2:
                                render_metric_with_help(
                                    "수익성/건전성",
                                    format_optional_number(getattr(stock, "financial_health_score", None)),
                                )
                            with s3:
                                render_metric_with_help(
                                    "3년 지속성",
                                    format_optional_number(getattr(stock, "financial_persistence_score", None)),
                                )
                            with s4:
                                render_metric_with_help(
                                    "밸류에이션",
                                    format_optional_number(getattr(stock, "valuation_score", None)),
                                )
                            with s5:
                                render_metric_with_help(
                                    "리스크 감점",
                                    format_optional_number(getattr(stock, "risk_penalty", None)),
                                )
                            p1, p2, p3 = st.columns(3)
                            with p1:
                                render_metric_with_help(
                                    "3년 매출 CAGR",
                                    format_optional_number(getattr(stock, "revenue_cagr_3y", None), suffix="%"),
                                )
                            with p2:
                                render_metric_with_help("섹터 순위", _format_sector_rank(stock))
                            with p3:
                                render_metric_with_help(
                                    "섹터 백분위",
                                    format_optional_percent(getattr(stock, "sector_percentile", None)),
                                )
                        
                        # 추가 재무 지표
                        if stock.debt_to_equity or stock.current_ratio or stock.pe_ratio:
                            c5, c6, c7 = st.columns(3)
                            if stock.debt_to_equity:
                                with c5:
                                    render_metric_with_help("부채비율", f"{stock.debt_to_equity:.1f}%")
                            if stock.current_ratio:
                                with c6:
                                    render_metric_with_help("유동비율", f"{stock.current_ratio:.2f}")
                            if stock.pe_ratio:
                                with c7:
                                    render_metric_with_help("PER", f"{stock.pe_ratio:.1f}")
                        
                        st.info(f"💡 **검토 근거**: {stock.reason}")
                        
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

    last_results = st.session_state.get("growth_last_results", [])
    if last_results:
        st.divider()
        st.subheader("💾 성장 후보 저장")
        save_cols = st.columns([1, 2])
        with save_cols[0]:
            snapshot_date = st.date_input(
                "스냅샷 날짜",
                value=st.session_state.get("growth_last_saved_at", date.today()),
                key="growth_snapshot_date",
            )
        with save_cols[1]:
            st.caption("저장된 후보는 `data/growth_candidates/growth_candidates_YYYYMMDD.csv`에 쌓이고, 성장 후보 전용 20일/60일 사후검증 입력으로 사용할 수 있습니다.")
            if st.button("현재 검토 후보 저장", use_container_width=True):
                try:
                    saved_path = save_growth_results_for_validation(
                        last_results,
                        snapshot_date=snapshot_date,
                    )
                    st.success(f"저장 완료: {saved_path}")
                except Exception as exc:
                    st.error(f"성장 후보 저장 실패: {exc}")
    
    # 안내 메시지
    st.markdown("---")
    st.subheader("🧪 사후 검증")

    st.markdown("#### 저장 성장 후보 20일/60일 검증")
    snapshot_files = list_growth_candidate_snapshot_files()
    if snapshot_files:
        validation_cols = st.columns([2, 1, 1])
        with validation_cols[0]:
            selected_snapshot = st.selectbox(
                "검증할 후보 파일",
                options=snapshot_files,
                format_func=lambda path: path.name,
                key="growth_validation_snapshot_file",
            )
        with validation_cols[1]:
            validation_threshold = st.number_input(
                "Hit 기준(%)",
                min_value=1.0,
                max_value=100.0,
                value=10.0,
                step=1.0,
                key="growth_validation_threshold",
            )
        with validation_cols[2]:
            run_saved_validation = st.button(
                "저장 후보 사후검증 실행",
                type="primary",
                use_container_width=True,
                key="growth_validation_run",
            )

        st.caption("저장된 성장 후보 CSV를 읽고 yfinance 가격 이력으로 후보 선정 이후 20영업일/60영업일 수익률을 계산합니다.")

        if run_saved_validation:
            try:
                snapshots = load_growth_candidate_snapshots(selected_snapshot)
                with st.spinner("저장 후보 가격 이력 조회 및 사후검증 실행 중..."):
                    histories = fetch_growth_validation_price_history(snapshots)
                    validation_results = validate_growth_candidates(
                        snapshots,
                        histories,
                        hit_threshold=float(validation_threshold),
                    )
                    validation_summary = summarize_validation(validation_results)

                valid_20d = sum(1 for result in validation_results if result.return_20d is not None)
                valid_60d = sum(1 for result in validation_results if result.return_60d is not None)

                st.success(f"검증 완료: {selected_snapshot.name}")
                mv1, mv2, mv3, mv4, mv5 = st.columns(5)
                mv1.metric("검증 후보", f"{validation_summary['total']}개")
                mv2.metric(
                    "20일 Hit Rate",
                    format_optional_percent(validation_summary["hit_rate_20d"] if valid_20d else None),
                )
                mv3.metric(
                    "20일 평균",
                    format_optional_number(
                        validation_summary["avg_return_20d"] if valid_20d else None,
                        suffix="%",
                    ),
                )
                mv4.metric(
                    "60일 Hit Rate",
                    format_optional_percent(validation_summary["hit_rate_60d"] if valid_60d else None),
                )
                mv5.metric(
                    "60일 평균",
                    format_optional_number(
                        validation_summary["avg_return_60d"] if valid_60d else None,
                        suffix="%",
                    ),
                )

                validation_df = growth_validation_results_to_dataframe(validation_results)
                st.dataframe(validation_df, use_container_width=True)

                if valid_20d < len(validation_results) or valid_60d < len(validation_results):
                    st.info("후보 선정일 이후 20/60영업일이 아직 지나지 않았거나 가격 이력이 부족한 종목은 N/A로 남습니다.")
            except Exception as exc:
                st.error(f"성장 후보 사후검증 실패: {exc}")
    else:
        st.info("저장된 성장 후보 CSV가 없습니다. 먼저 성장 가능성 주를 찾은 뒤 `현재 검토 후보 저장`을 눌러주세요.")

    st.markdown("#### 조기신호 백테스트")
    today = date.today()
    default_start = today - timedelta(days=60)
    backtest_cols = st.columns([1, 1, 1, 1])
    with backtest_cols[0]:
        bt_start = st.date_input("검증 시작일", value=default_start, key="growth_bt_start")
    with backtest_cols[1]:
        bt_end = st.date_input("검증 종료일", value=today, key="growth_bt_end")
    with backtest_cols[2]:
        bt_horizons = st.text_input("관찰 영업일", value="1,3,5", key="growth_bt_horizons")
    with backtest_cols[3]:
        bt_threshold = st.number_input("급등 기준(%)", min_value=1, max_value=50, value=15, key="growth_bt_threshold")

    command = build_growth_backtest_command(
        start=bt_start,
        end=bt_end,
        horizons=bt_horizons,
        surge_threshold=int(bt_threshold),
    )
    st.caption("시장흐름의 조기신호_관찰과 KR 급등주 데이터를 기준으로 검증합니다.")

    if st.button("조기신호 백테스트 실행", use_container_width=True, key="growth_backtest_run"):
        try:
            with st.spinner("조기신호 백테스트 실행 중..."):
                completed = run_growth_backtest(
                    start=bt_start,
                    end=bt_end,
                    horizons=bt_horizons,
                    surge_threshold=int(bt_threshold),
                )
            if completed.returncode == 0:
                st.success("조기신호 백테스트 실행 완료")
            else:
                st.error(f"조기신호 백테스트 실패(returncode={completed.returncode})")

            if completed.stdout:
                st.code(completed.stdout[-4000:], language="text")
            if completed.stderr:
                st.code(completed.stderr[-4000:], language="text")
        except subprocess.TimeoutExpired:
            st.error("조기신호 백테스트가 제한 시간 내에 끝나지 않았습니다.")
        except Exception as exc:
            st.error(f"조기신호 백테스트 실행 실패: {exc}")

    with st.expander("실행 명령 확인", expanded=False):
        st.code(command, language="powershell")

    latest_report = find_latest_backtest_report()
    if latest_report:
        with st.expander(f"최신 백테스트 리포트 미리보기: {latest_report.name}", expanded=False):
            st.markdown(read_backtest_report_preview(latest_report))
    else:
        st.info("아직 reports/backtest_*.md 리포트가 없습니다. 위 명령을 실행하면 리포트가 생성됩니다.")

    st.markdown("---")
    st.markdown("""
    ### 📌 분석 방법
    **1단계: 실시간 시장 스캔**
    - KR: KOSPI/KOSDAQ 전체, US: NYSE/NASDAQ/AMEX 스캐너
    - 거래대금과 당일 관심도로 1차 압축
    - 상위 후보만 6개월 일봉으로 5일/20일 또는 60일 모멘텀, 거래량 증가, 고점 근접도 계산

    **2단계: Yahoo Finance 재무 스크리닝**
    - 매출 성장률 10% 이상
    - 부채비율 150% 이하
    - 유동비율 1.0 이상
    - 시가총액 $50B 미만 (중소형)
    
    **3단계: Tavily 웹 검색 (API 키 입력 시)**
    - 최신 뉴스 및 트렌드 분석
    - 감성 분석은 참고 신호로 사용
    
    > ⚠️ **주의**: 본 추천은 참고용이며, 투자 조언이 아닙니다.
    """)
