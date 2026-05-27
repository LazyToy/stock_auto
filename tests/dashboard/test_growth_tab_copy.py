from pathlib import Path


def test_growth_tab_uses_review_candidate_language():
    source = Path("dashboard/components/growth_tab.py").read_text(encoding="utf-8")

    assert "검토 후보 Top 5" in source
    assert "검토 근거" in source
    assert "추천 종목 Top 5" not in source
    assert "추천 사유" not in source


def test_growth_tab_has_clickable_term_explanations():
    source = Path("dashboard/components/growth_tab.py").read_text(encoding="utf-8")

    assert "TERM_EXPLANATIONS" in source
    assert "render_metric_with_help" in source
    assert "help=explanation" in source
    assert "st.popover" not in source
    for term in ["현재가", "성장 점수", "수급 점수", "5일 스마트머니", "최근 1일 외국인", "PER"]:
        assert term in source
