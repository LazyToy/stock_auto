"""이슈 #11: 수급 전환 시그널 판정 단위 테스트."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def test_detect_reversal_foreign_buy():
    """5일 연속 외국인 순매도 후 당일 순매수 → 매수전환 감지."""
    from flow_signal import detect_reversal
    records = [
        {"date": "2026.04.17", "foreign": 15234, "institution": -100},
        {"date": "2026.04.16", "foreign": -3100, "institution": -200},
        {"date": "2026.04.15", "foreign": -5200, "institution": -100},
        {"date": "2026.04.14", "foreign": -2800, "institution": +500},
        {"date": "2026.04.11", "foreign": -1500, "institution": -300},
        {"date": "2026.04.10", "foreign": -900,  "institution": -400},
    ]
    signals = detect_reversal(records, lookback=5)
    assert any(s["reversal_type"] == "외국인매수전환" for s in signals)


def test_detect_reversal_not_enough_history():
    """이력이 5일 미만이면 전환 감지 안 함."""
    from flow_signal import detect_reversal
    records = [
        {"date": "2026.04.17", "foreign": 5000, "institution": -100},
        {"date": "2026.04.16", "foreign": -3100, "institution": -200},
    ]
    signals = detect_reversal(records, lookback=5)
    assert signals == []


def test_detect_reversal_no_reversal_today_also_negative():
    """당일도 순매도면 외국인매수전환 없음."""
    from flow_signal import detect_reversal
    records = [
        {"date": "2026.04.17", "foreign": -1000, "institution": -100},
        {"date": "2026.04.16", "foreign": -3100, "institution": -200},
        {"date": "2026.04.15", "foreign": -5200, "institution": -100},
        {"date": "2026.04.14", "foreign": -2800, "institution": +500},
        {"date": "2026.04.11", "foreign": -1500, "institution": -300},
        {"date": "2026.04.10", "foreign": -900,  "institution": -400},
    ]
    signals = detect_reversal(records, lookback=5)
    assert not any(s["reversal_type"] == "외국인매수전환" for s in signals)


def test_detect_reversal_institution_sell_reversal():
    """기관 매도전환 감지 (5일 연속 순매수 → 당일 순매도)."""
    from flow_signal import detect_reversal
    records = [
        {"date": "2026.04.17", "foreign": -500,  "institution": -8000},
        {"date": "2026.04.16", "foreign": +200,  "institution": 3000},
        {"date": "2026.04.15", "foreign": +100,  "institution": 2000},
        {"date": "2026.04.14", "foreign": +300,  "institution": 1000},
        {"date": "2026.04.11", "foreign": +150,  "institution": 500},
        {"date": "2026.04.10", "foreign": +80,   "institution": 200},
    ]
    signals = detect_reversal(records, lookback=5)
    assert any(s["reversal_type"] == "기관매도전환" for s in signals)


def test_detect_reversal_institution_buy_reversal():
    """기관 매수전환 감지 (5일 연속 순매도 → 당일 순매수)."""
    from flow_signal import detect_reversal
    records = [
        {"date": "2026.04.17", "foreign": 100,   "institution": 5000},
        {"date": "2026.04.16", "foreign": -200,  "institution": -1000},
        {"date": "2026.04.15", "foreign": -100,  "institution": -2000},
        {"date": "2026.04.14", "foreign": -300,  "institution": -1500},
        {"date": "2026.04.11", "foreign": -150,  "institution": -800},
        {"date": "2026.04.10", "foreign": -80,   "institution": -600},
    ]
    signals = detect_reversal(records, lookback=5)
    assert any(s["reversal_type"] == "기관매수전환" for s in signals)


def test_build_flow_signal_row():
    """시트 row 직렬화 검증."""
    from flow_signal import build_flow_signal_row
    row = build_flow_signal_row(
        date="2026-04-17",
        ticker="005930",
        name="삼성전자",
        reversal_type="외국인매수전환",
        today_foreign=15234,
        today_institution=-8450,
        prev_days_foreign=[-3100, -5200, -2800, -1500, -900],
        prev_days_institution=[-200, -100, 500, -300, -400],
    )
    assert row[0] == "2026-04-17"
    assert row[1] == "005930"
    assert row[2] == "삼성전자"
    assert row[3] == "외국인매수전환"
    assert row[4] == 15234
    assert row[5] == -8450
    assert row[6] == sum([-3100, -5200, -2800, -1500, -900])
    assert row[7] == sum([-200, -100, 500, -300, -400])


if __name__ == "__main__":
    test_detect_reversal_foreign_buy()
    test_detect_reversal_not_enough_history()
    test_detect_reversal_no_reversal_today_also_negative()
    test_detect_reversal_institution_sell_reversal()
    test_detect_reversal_institution_buy_reversal()
    test_build_flow_signal_row()
    print("[PASS] test_flow_signal 전체 통과")
