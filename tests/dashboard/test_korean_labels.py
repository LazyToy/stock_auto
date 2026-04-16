from pathlib import Path
from unittest.mock import patch

from dashboard.label_utils import localize_signal_terms, normalize_signal, signal_to_korean
from dashboard.symbol_utils import build_chart_title, build_symbol_label, format_symbol_label, normalize_symbol_code


def test_dashboard_uses_korean_labels_for_deep_analysis_and_agent_debate():
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "🧠 심층 분석" in text
    assert "💬 AI 에이전트 토론" in text
    assert "🧠 Multimodal Deep Analysis" not in text
    assert "💬 Multi-Agent Debate Consensus" not in text
    assert "🚀 토론 시작" in text
    assert "🚀 Start Debate" not in text
    assert "최종 판정" in text
    assert "신호" in text


def test_signal_to_korean_maps_runtime_labels():
    assert signal_to_korean("BUY") == "매수"
    assert signal_to_korean("SELL") == "매도"
    assert signal_to_korean("HOLD") == "보유"
    assert signal_to_korean("NEUTRAL") == "중립"


def test_normalize_signal_accepts_korean_and_english_inputs():
    assert normalize_signal("매수") == "BUY"
    assert normalize_signal("매도") == "SELL"
    assert normalize_signal("보유") == "HOLD"
    assert normalize_signal("중립") == "NEUTRAL"
    assert normalize_signal("BUY") == "BUY"


def test_localize_signal_terms_rewrites_english_decision_words():
    text = "Final Verdict: BUY, not HOLD."
    localized = localize_signal_terms(text)
    assert "매수" in localized
    assert "보유" in localized
    assert "BUY" not in localized
    assert "HOLD" not in localized


def test_dashboard_uses_streamlit_legacy_image_width_arg():
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "st.image(chart_buf, use_column_width=True)" in text


def test_symbol_label_formats_known_symbols():
    assert normalize_symbol_code("005930.KS") == "005930"
    assert normalize_symbol_code("aapl") == "AAPL"
    assert format_symbol_label("005930", "삼성전자") == "005930 (삼성전자)"
    assert format_symbol_label("AAPL", "Apple") == "AAPL (Apple)"


@patch("yfinance.Ticker")
def test_build_symbol_label_skips_invalid_ks_name_and_uses_equity_candidate(mock_ticker):
    bad_ks = type("Ticker", (), {"info": {"shortName": "317330.KS,0P0001I5WP,279919", "quoteType": "MUTUALFUND"}})()
    good_kq = type("Ticker", (), {"info": {"shortName": "Duksan Techopia", "longName": "DUKSAN TECHOPIA Co.,Ltd.", "quoteType": "EQUITY"}})()

    mock_ticker.side_effect = [bad_ks, good_kq]

    assert build_symbol_label("317330") == "317330 (DUKSAN TECHOPIA Co.,Ltd.)"


def test_dashboard_wires_symbol_labels_into_analysis_and_debate_flows():
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "analysis_symbol_label = build_symbol_label(ticker_input)" in text
    assert 'st.caption(f"선택 종목: {analysis_symbol_label}")' in text
    assert "debate_symbol_label = build_symbol_label(debate_ticker)" in text
    assert 'st.info(f"선택된 종목: **{debate_symbol_label}**")' in text


def test_dashboard_shows_symbol_label_in_chart_analysis_section():
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "chart_symbol_label = build_symbol_label(chart_symbol or ticker_input)" in text
    assert 'st.caption(f"차트 기준 종목: {chart_symbol_label}")' in text


def test_dashboard_shows_technical_indicator_summary_in_deep_analysis():
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert 'technical_summary = result.get("technical_summary", "")' in text
    assert 'st.markdown("**기술 지표 요약**")' in text
    assert 'st.text(technical_summary)' in text


def test_build_chart_title_uses_symbol_label_when_available():
    assert build_chart_title("317330", "DUKSAN TECHOPIA Co.,Ltd.") == "317330 (DUKSAN TECHOPIA Co.,Ltd.) 분석"
    assert build_chart_title("AAPL", "Apple") == "AAPL (Apple) 분석"


@patch("yfinance.Ticker")
def test_build_symbol_label_hides_mojibake_company_name_for_unknown_kr_symbol(mock_ticker):
    garbled_name = "ì¼ì±ì ì"
    garbled = type("Ticker", (), {"info": {"shortName": garbled_name, "quoteType": "EQUITY"}})()

    mock_ticker.side_effect = [garbled, garbled]

    assert build_symbol_label("123456") == "123456"
