"""
이슈 #14: 조기신호→급등주 연결 백테스트 단위 테스트.

* 통계 함수, 수익률 계산, 섹터 hit rate 는 순수 함수로 분리해 테스트.
* 시트/네트워크 I/O 는 inject 해서 fake 로 교체.
* 산출 리포트는 markdown 텍스트로 검증.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ---------------------------------------------------------------------------
# compute_horizon_returns — 신호일 종가 대비 +N영업일 종가 수익률
# ---------------------------------------------------------------------------

def test_compute_horizon_returns_basic():
    """신호일 close=100, +1=105, +3=110, +5=120 → 각각 5/10/20%"""
    from backtest_early_signal import compute_horizon_returns

    closes = {
        ("005930", "2026-04-10"): 100.0,
        ("005930", "2026-04-13"): 105.0,
        ("005930", "2026-04-15"): 110.0,
        ("005930", "2026-04-17"): 120.0,
    }

    def lookup(t, d):
        return closes.get((t, d))

    rets = compute_horizon_returns(
        ticker="005930",
        signal_date="2026-04-10",
        horizons=[1, 3, 5],
        close_lookup=lookup,
    )
    assert abs(rets[1] - 5.0) < 1e-6
    assert abs(rets[3] - 10.0) < 1e-6
    assert abs(rets[5] - 20.0) < 1e-6


def test_compute_horizon_returns_missing_data_returns_none():
    """미래 종가 조회 실패 시 해당 horizon 만 None."""
    from backtest_early_signal import compute_horizon_returns

    closes = {
        ("AAA", "2026-04-10"): 100.0,
        ("AAA", "2026-04-13"): 105.0,
        # +3, +5 없음
    }

    def lookup(t, d):
        return closes.get((t, d))

    rets = compute_horizon_returns(
        ticker="AAA",
        signal_date="2026-04-10",
        horizons=[1, 3, 5],
        close_lookup=lookup,
    )
    assert abs(rets[1] - 5.0) < 1e-6
    assert rets[3] is None
    assert rets[5] is None


def test_compute_horizon_returns_zero_base_returns_none():
    """신호일 종가가 0 이하면 모든 horizon None (lookahead bias 방어)."""
    from backtest_early_signal import compute_horizon_returns

    def lookup(t, d):
        if d == "2026-04-10":
            return 0.0
        return 100.0

    rets = compute_horizon_returns(
        ticker="X",
        signal_date="2026-04-10",
        horizons=[1, 3, 5],
        close_lookup=lookup,
    )
    assert rets == {1: None, 3: None, 5: None}


# ---------------------------------------------------------------------------
# summarize_returns — median, q25, q75, win rate, count
# ---------------------------------------------------------------------------

def test_summarize_returns_basic_quartiles():
    """[-10, 0, 10, 20] → median=5, q25=-2.5, q75=12.5, win_rate=0.5, n=4"""
    from backtest_early_signal import summarize_returns
    summary = summarize_returns([-10.0, 0.0, 10.0, 20.0])
    assert summary["count"] == 4
    assert abs(summary["median"] - 5.0) < 1e-6
    assert abs(summary["q25"] - (-2.5)) < 1e-6
    assert abs(summary["q75"] - 12.5) < 1e-6
    # win = 양수 비율 (0 은 미포함, 0이면 'flat')
    assert abs(summary["win_rate"] - 0.5) < 1e-6


def test_summarize_returns_empty_input():
    """빈 입력 시 모든 통계는 0.0, count=0, win_rate=0.0."""
    from backtest_early_signal import summarize_returns
    summary = summarize_returns([])
    assert summary["count"] == 0
    assert summary["median"] == 0.0
    assert summary["q25"] == 0.0
    assert summary["q75"] == 0.0
    assert summary["win_rate"] == 0.0


def test_summarize_returns_drops_none():
    """None 은 통계 계산에서 제외."""
    from backtest_early_signal import summarize_returns
    summary = summarize_returns([None, 10.0, None, 20.0])  # type: ignore[list-item]
    assert summary["count"] == 2
    assert abs(summary["median"] - 15.0) < 1e-6
    assert abs(summary["win_rate"] - 1.0) < 1e-6


def test_summarize_returns_all_losses_zero_win_rate():
    from backtest_early_signal import summarize_returns
    summary = summarize_returns([-1.0, -2.0, -3.0])
    assert summary["count"] == 3
    assert summary["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# compute_surge_hit_rate — 조기신호 중 실제 15%+ 급등 진입 비율
# ---------------------------------------------------------------------------

def test_compute_surge_hit_rate_basic():
    """3종목 중 1종목만 +15% 도달 → 1/3."""
    from backtest_early_signal import compute_surge_hit_rate
    # row format: {"ticker", "signal_date", "max_return_5d"}
    signals = [
        {"ticker": "A", "signal_date": "2026-04-10", "max_return_5d": 16.0},
        {"ticker": "B", "signal_date": "2026-04-10", "max_return_5d": 5.0},
        {"ticker": "C", "signal_date": "2026-04-10", "max_return_5d": 14.99},
    ]
    rate = compute_surge_hit_rate(signals, threshold=15.0)
    assert abs(rate - (1.0 / 3.0)) < 1e-6


def test_compute_surge_hit_rate_empty():
    from backtest_early_signal import compute_surge_hit_rate
    assert compute_surge_hit_rate([], threshold=15.0) == 0.0


def test_compute_surge_hit_rate_skips_none_max():
    """max_return_5d 가 None 인 signal 은 분모에서 제외 (survivorship 방어)."""
    from backtest_early_signal import compute_surge_hit_rate
    signals = [
        {"ticker": "A", "signal_date": "2026-04-10", "max_return_5d": 20.0},
        {"ticker": "B", "signal_date": "2026-04-10", "max_return_5d": None},
    ]
    assert compute_surge_hit_rate(signals, threshold=15.0) == 1.0


# ---------------------------------------------------------------------------
# compute_sector_hit_rate — 섹터별 hit rate
# ---------------------------------------------------------------------------

def test_compute_sector_hit_rate_basic():
    """섹터별 분포 검증."""
    from backtest_early_signal import compute_sector_hit_rate
    signals = [
        {"ticker": "A", "sector": "2차전지", "max_return_5d": 16.0},
        {"ticker": "B", "sector": "2차전지", "max_return_5d": 4.0},
        {"ticker": "C", "sector": "바이오", "max_return_5d": 20.0},
    ]
    result = compute_sector_hit_rate(signals, threshold=15.0)
    assert result["2차전지"]["hit"] == 1
    assert result["2차전지"]["total"] == 2
    assert abs(result["2차전지"]["rate"] - 0.5) < 1e-6
    assert result["바이오"]["hit"] == 1
    assert result["바이오"]["total"] == 1
    assert result["바이오"]["rate"] == 1.0


def test_compute_sector_hit_rate_skips_unknown_sector():
    """sector 키 누락된 신호는 미분류('미분류')로 분류."""
    from backtest_early_signal import compute_sector_hit_rate
    signals = [
        {"ticker": "X", "max_return_5d": 20.0},  # sector 없음
    ]
    result = compute_sector_hit_rate(signals, threshold=15.0)
    assert "미분류" in result
    assert result["미분류"]["total"] == 1


# ---------------------------------------------------------------------------
# load_early_signals_from_sheet — 시트 fake 로 행 파싱
# ---------------------------------------------------------------------------

class _FakeWorksheet:
    def __init__(self, rows):
        self._rows = [list(r) for r in rows]

    def get_all_values(self):
        return [list(r) for r in self._rows]


class _FakeMarketFlowSheet:
    def __init__(self, rows):
        from daily_trend_writer import EARLY_SIGNAL_HEADERS
        self._ws = _FakeWorksheet([list(EARLY_SIGNAL_HEADERS)] + list(rows))

    def _ensure_worksheet(self, title, headers):
        return self._ws


def test_load_early_signals_filters_by_date_range():
    """시작일~종료일 범위 필터링."""
    from backtest_early_signal import load_early_signals
    rows = [
        ["2026-03-01", "A", "name", 5.0, 3.0, 3, 0.95, 100.0, ""],
        ["2026-04-10", "B", "name", 5.0, 3.0, 3, 0.95, 100.0, ""],
        ["2026-04-20", "C", "name", 5.0, 3.0, 3, 0.95, 100.0, ""],
    ]
    sheet = _FakeMarketFlowSheet(rows)
    signals = load_early_signals(
        sheet,
        start_date=_dt.date(2026, 4, 1),
        end_date=_dt.date(2026, 4, 15),
    )
    assert [s["ticker"] for s in signals] == ["B"]
    assert signals[0]["signal_date"] == "2026-04-10"


def test_load_early_signals_skips_blank_or_invalid_rows():
    from backtest_early_signal import load_early_signals
    rows = [
        ["", "", "", "", "", "", "", "", ""],
        ["bad-date", "X", "name", 5.0, 3.0, 3, 0.95, 100.0, ""],
        ["2026-04-10", "B", "name", 5.0, 3.0, 3, 0.95, 100.0, ""],
    ]
    sheet = _FakeMarketFlowSheet(rows)
    signals = load_early_signals(
        sheet,
        start_date=_dt.date(2026, 1, 1),
        end_date=_dt.date(2026, 12, 31),
    )
    assert [s["ticker"] for s in signals] == ["B"]


# ---------------------------------------------------------------------------
# render_report — markdown 출력
# ---------------------------------------------------------------------------

def test_render_report_contains_required_sections():
    """리포트에 median, q25, q75, win_rate, hit_rate 가 포함된다."""
    from backtest_early_signal import render_report

    horizon_summary = {
        1: {"count": 10, "median": 1.5, "q25": -1.0, "q75": 4.0, "win_rate": 0.6},
        3: {"count": 10, "median": 3.2, "q25": 0.5, "q75": 7.0, "win_rate": 0.7},
        5: {"count": 10, "median": 5.0, "q25": 1.0, "q75": 9.5, "win_rate": 0.7},
    }
    surge_hit_rate = 0.25
    sector_table = {
        "2차전지": {"hit": 2, "total": 5, "rate": 0.4},
        "바이오":   {"hit": 1, "total": 3, "rate": 1.0 / 3.0},
    }
    md = render_report(
        title="조기신호 백테스트 리포트",
        period=("2026-03-01", "2026-04-17"),
        signal_count=10,
        horizon_summary=horizon_summary,
        surge_threshold=15.0,
        surge_hit_rate=surge_hit_rate,
        sector_table=sector_table,
        notes={
            "entry_price": "신호일 종가",
            "survivorship": "조회 실패 종목은 분모 제외",
        },
    )

    assert "조기신호 백테스트 리포트" in md
    assert "2026-03-01" in md and "2026-04-17" in md
    assert "median" in md.lower()
    assert "q25" in md.lower()
    assert "q75" in md.lower()
    assert "win" in md.lower()
    # 섹터 표
    assert "2차전지" in md
    assert "바이오" in md
    # 진입 비율
    assert "25.00%" in md or "25.0%" in md
    # 가정/한계 노트
    assert "신호일 종가" in md
    assert "분모 제외" in md


def test_render_report_handles_empty_signals():
    from backtest_early_signal import render_report
    md = render_report(
        title="빈 리포트",
        period=("2026-04-01", "2026-04-17"),
        signal_count=0,
        horizon_summary={
            1: {"count": 0, "median": 0.0, "q25": 0.0, "q75": 0.0, "win_rate": 0.0},
        },
        surge_threshold=15.0,
        surge_hit_rate=0.0,
        sector_table={},
        notes={"entry_price": "신호일 종가", "survivorship": "n/a"},
    )
    assert "신호 0건" in md or "0건" in md


# ---------------------------------------------------------------------------
# build_cli_parser — argparse 검증
# ---------------------------------------------------------------------------

def test_build_cli_parser_accepts_period_and_horizons():
    from backtest_early_signal import build_cli_parser
    parser = build_cli_parser()
    args = parser.parse_args([
        "--start", "2026-03-01",
        "--end", "2026-04-17",
        "--horizons", "1,3,5",
        "--surge-threshold", "15",
        "--output", "reports/test.md",
    ])
    assert args.start == "2026-03-01"
    assert args.end == "2026-04-17"
    assert args.horizons == "1,3,5"
    assert abs(float(args.surge_threshold) - 15.0) < 1e-6
    assert args.output == "reports/test.md"


def test_build_cli_parser_optional_sector_filter():
    from backtest_early_signal import build_cli_parser
    parser = build_cli_parser()
    args = parser.parse_args([
        "--start", "2026-01-01",
        "--end", "2026-04-17",
        "--sector", "2차전지",
    ])
    assert args.sector == "2차전지"


def test_build_cli_parser_defaults_horizons():
    """기본 horizons 가 1,3,5 인지."""
    from backtest_early_signal import build_cli_parser, parse_horizons
    parser = build_cli_parser()
    args = parser.parse_args(["--start", "2026-01-01", "--end", "2026-04-17"])
    assert parse_horizons(args.horizons) == [1, 3, 5]


def test_parse_horizons_csv():
    from backtest_early_signal import parse_horizons
    assert parse_horizons("1,3,5") == [1, 3, 5]
    assert parse_horizons("2,7,10") == [2, 7, 10]
    # 공백 허용
    assert parse_horizons("1, 3 , 5") == [1, 3, 5]


# ---------------------------------------------------------------------------
# enrich_signals_with_returns — end-to-end injectable 흐름
# ---------------------------------------------------------------------------

def test_enrich_signals_with_returns_adds_horizons_and_max():
    """각 신호에 returns_by_horizon, max_return_5d 가 추가된다."""
    from backtest_early_signal import enrich_signals_with_returns

    closes = {
        ("A", "2026-04-10"): 100.0,
        ("A", "2026-04-13"): 105.0,
        ("A", "2026-04-15"): 116.0,
        ("A", "2026-04-17"): 110.0,
    }

    def lookup(t, d):
        return closes.get((t, d))

    signals = [
        {"ticker": "A", "signal_date": "2026-04-10"},
    ]
    enriched = enrich_signals_with_returns(
        signals, horizons=[1, 3, 5], close_lookup=lookup
    )
    assert "returns_by_horizon" in enriched[0]
    assert abs(enriched[0]["returns_by_horizon"][1] - 5.0) < 1e-6
    assert abs(enriched[0]["returns_by_horizon"][3] - 16.0) < 1e-6
    assert abs(enriched[0]["returns_by_horizon"][5] - 10.0) < 1e-6
    # max_return_5d 는 1..5일 max 수익률 (없으면 None)
    assert abs(enriched[0]["max_return_5d"] - 16.0) < 1e-6


def test_enrich_signals_with_returns_max_none_when_all_missing():
    from backtest_early_signal import enrich_signals_with_returns

    def lookup(t, d):
        # 신호일만 있고 미래 close 없음 → 모두 None
        return 100.0 if d == "2026-04-10" else None

    enriched = enrich_signals_with_returns(
        [{"ticker": "B", "signal_date": "2026-04-10"}],
        horizons=[1, 3, 5],
        close_lookup=lookup,
    )
    assert enriched[0]["max_return_5d"] is None


# ---------------------------------------------------------------------------
# validate_period — AC-1: 1개월 이상 이력 강제
# ---------------------------------------------------------------------------

def test_validate_period_rejects_end_before_start():
    from backtest_early_signal import validate_period
    ok, msg = validate_period(_dt.date(2026, 4, 10), _dt.date(2026, 4, 1))
    assert ok is False
    assert msg


def test_validate_period_rejects_shorter_than_min_days():
    """기간이 min_days 미만이면 fail. 기본 28일."""
    from backtest_early_signal import validate_period
    ok, msg = validate_period(_dt.date(2026, 4, 1), _dt.date(2026, 4, 10))
    assert ok is False
    assert "1개월" in msg or "28" in msg or "min" in msg.lower()


def test_validate_period_accepts_exactly_min_days():
    from backtest_early_signal import validate_period
    ok, _msg = validate_period(
        _dt.date(2026, 3, 1), _dt.date(2026, 3, 29), min_days=28
    )
    assert ok is True


def test_validate_period_custom_min_days():
    """min_days 오버라이드 시 그에 맞게 판정."""
    from backtest_early_signal import validate_period
    ok1, _ = validate_period(_dt.date(2026, 4, 1), _dt.date(2026, 4, 10), min_days=5)
    assert ok1 is True
    ok2, _ = validate_period(_dt.date(2026, 4, 1), _dt.date(2026, 4, 10), min_days=30)
    assert ok2 is False


# ---------------------------------------------------------------------------
# apply_signal_filters — AC-3: 조건 필터 (change/RVOL/streak/52w)
# ---------------------------------------------------------------------------

def test_apply_signal_filters_min_change():
    from backtest_early_signal import apply_signal_filters
    signals = [
        {"ticker": "A", "change": 3.0, "rvol": 2.0, "streak": 3, "close_ratio_52w": 0.9},
        {"ticker": "B", "change": 7.0, "rvol": 2.0, "streak": 3, "close_ratio_52w": 0.9},
    ]
    out = apply_signal_filters(signals, {"min_change": 5.0})
    assert [s["ticker"] for s in out] == ["B"]


def test_apply_signal_filters_max_change():
    from backtest_early_signal import apply_signal_filters
    signals = [
        {"ticker": "A", "change": 8.0},
        {"ticker": "B", "change": 12.0},
    ]
    out = apply_signal_filters(signals, {"max_change": 10.0})
    assert [s["ticker"] for s in out] == ["A"]


def test_apply_signal_filters_rvol_streak_52w_combined():
    from backtest_early_signal import apply_signal_filters
    signals = [
        {"ticker": "A", "rvol": 1.0, "streak": 3, "close_ratio_52w": 0.95},
        {"ticker": "B", "rvol": 3.0, "streak": 1, "close_ratio_52w": 0.95},
        {"ticker": "C", "rvol": 3.0, "streak": 3, "close_ratio_52w": 0.80},
        {"ticker": "D", "rvol": 3.0, "streak": 3, "close_ratio_52w": 0.95},
    ]
    out = apply_signal_filters(
        signals,
        {"min_rvol": 2.0, "min_streak": 3, "min_ratio_52w": 0.9},
    )
    assert [s["ticker"] for s in out] == ["D"]


def test_apply_signal_filters_empty_returns_input():
    from backtest_early_signal import apply_signal_filters
    signals = [{"ticker": "A", "change": 3.0}]
    assert apply_signal_filters(signals, {}) == signals


# ---------------------------------------------------------------------------
# compute_max_return_over_window — 모든 +1..+N 영업일 스캔 (논리결함 #1)
# ---------------------------------------------------------------------------

def test_compute_max_return_over_window_picks_intermediate_peak():
    """+1=5%, +2=20%(peak), +3=10%, +4=2%, +5=-5% → max=20% at +2.

    horizons(1,3,5) 만 스캔하는 기존 버그를 차단: peak 가 +2 라도 잡혀야 함.
    """
    from backtest_early_signal import compute_max_return_over_window

    closes = {
        ("A", "2026-04-10"): 100.0,
        ("A", "2026-04-13"): 105.0,  # +1 bday
        ("A", "2026-04-14"): 120.0,  # +2 bday  ← peak
        ("A", "2026-04-15"): 110.0,  # +3 bday
        ("A", "2026-04-16"): 102.0,  # +4 bday
        ("A", "2026-04-17"):  95.0,  # +5 bday
    }

    def lookup(t, d):
        return closes.get((t, d))

    max_ret, hit_day = compute_max_return_over_window(
        ticker="A",
        signal_date="2026-04-10",
        window_bdays=5,
        close_lookup=lookup,
    )
    assert abs(max_ret - 20.0) < 1e-6
    assert hit_day == 2


def test_compute_max_return_over_window_all_missing_returns_none():
    from backtest_early_signal import compute_max_return_over_window

    def lookup(t, d):
        return 100.0 if d == "2026-04-10" else None

    max_ret, hit_day = compute_max_return_over_window(
        ticker="A",
        signal_date="2026-04-10",
        window_bdays=5,
        close_lookup=lookup,
    )
    assert max_ret is None
    assert hit_day is None


def test_compute_max_return_over_window_zero_base_returns_none():
    from backtest_early_signal import compute_max_return_over_window

    def lookup(t, d):
        return 0.0 if d == "2026-04-10" else 200.0

    max_ret, hit_day = compute_max_return_over_window(
        ticker="A",
        signal_date="2026-04-10",
        window_bdays=5,
        close_lookup=lookup,
    )
    assert max_ret is None
    assert hit_day is None


def test_enrich_signals_with_returns_uses_window_scan_for_max():
    """enrich_signals_with_returns 의 max_return_5d 도 +1..+5 전구간 스캔을 써야 한다.

    horizons=[1,3,5] 이어도, +2/+4 에 peak 이 있으면 반드시 그 값이 잡혀야 함.
    """
    from backtest_early_signal import enrich_signals_with_returns

    closes = {
        ("A", "2026-04-10"): 100.0,
        ("A", "2026-04-13"): 103.0,   # +1
        ("A", "2026-04-14"): 125.0,   # +2  ← peak, horizons 에 없음
        ("A", "2026-04-15"): 108.0,   # +3
        ("A", "2026-04-16"): 105.0,   # +4
        ("A", "2026-04-17"): 102.0,   # +5
    }

    def lookup(t, d):
        return closes.get((t, d))

    enriched = enrich_signals_with_returns(
        [{"ticker": "A", "signal_date": "2026-04-10"}],
        horizons=[1, 3, 5],
        close_lookup=lookup,
    )
    assert abs(enriched[0]["max_return_5d"] - 25.0) < 1e-6


# ---------------------------------------------------------------------------
# compute_surge_sheet_hit_rate — 실제 급등주 시트(15%+) 진입 매칭 (논리결함 #2)
# ---------------------------------------------------------------------------

def test_compute_surge_sheet_hit_rate_matches_actual_entries():
    """조기신호 후 +N영업일 내에 급등주 시트에 ticker 가 등재된 경우만 hit 로 계산."""
    from backtest_early_signal import compute_surge_sheet_hit_rate

    signals = [
        {"ticker": "005930", "signal_date": "2026-04-10"},
        {"ticker": "000660", "signal_date": "2026-04-10"},
        {"ticker": "035720", "signal_date": "2026-04-10"},
    ]
    # 급등주 시트의 (ticker, 등재일) 튜플들
    surge_entries = [
        ("005930", "2026-04-13"),   # +1 bday → hit
        ("035720", "2026-04-30"),   # +14 bday → window 밖 → miss
    ]
    rate = compute_surge_sheet_hit_rate(
        signals, surge_entries=surge_entries, within_bdays=5
    )
    assert abs(rate - (1.0 / 3.0)) < 1e-6


def test_compute_surge_sheet_hit_rate_normalizes_kr_ticker_zfill():
    """KR ticker 는 zfill(6) 적용되어 '5930' 과 '005930' 이 일치해야 한다."""
    from backtest_early_signal import compute_surge_sheet_hit_rate

    signals = [{"ticker": "005930", "signal_date": "2026-04-10"}]
    surge_entries = [("5930", "2026-04-13")]  # leading-zero 없는 변종
    rate = compute_surge_sheet_hit_rate(
        signals, surge_entries=surge_entries, within_bdays=5
    )
    assert rate == 1.0


def test_compute_surge_sheet_hit_rate_normalizes_us_ticker_upper():
    """US ticker 는 upper() 로 대소문자 무시."""
    from backtest_early_signal import compute_surge_sheet_hit_rate

    signals = [{"ticker": "aapl", "signal_date": "2026-04-10"}]
    surge_entries = [("AAPL", "2026-04-13")]
    rate = compute_surge_sheet_hit_rate(
        signals, surge_entries=surge_entries, within_bdays=5
    )
    assert rate == 1.0


def test_compute_surge_sheet_hit_rate_empty_entries_zero():
    from backtest_early_signal import compute_surge_sheet_hit_rate
    signals = [{"ticker": "A", "signal_date": "2026-04-10"}]
    assert compute_surge_sheet_hit_rate(signals, surge_entries=[], within_bdays=5) == 0.0


def test_compute_surge_sheet_hit_rate_no_double_count_same_ticker():
    """같은 ticker 가 여러 날 급등주 시트에 등재돼도 hit 는 1회."""
    from backtest_early_signal import compute_surge_sheet_hit_rate

    signals = [{"ticker": "A", "signal_date": "2026-04-10"}]
    surge_entries = [
        ("A", "2026-04-13"),
        ("A", "2026-04-14"),
        ("A", "2026-04-15"),
    ]
    rate = compute_surge_sheet_hit_rate(signals, surge_entries=surge_entries, within_bdays=5)
    assert rate == 1.0


# ---------------------------------------------------------------------------
# count_dropped_survivorship — 수익률 조회 실패 건수 보고 (논리결함 #3)
# ---------------------------------------------------------------------------

def test_count_dropped_survivorship_counts_none_max():
    from backtest_early_signal import count_dropped_survivorship
    enriched = [
        {"ticker": "A", "max_return_5d": 10.0},
        {"ticker": "B", "max_return_5d": None},
        {"ticker": "C", "max_return_5d": None},
        {"ticker": "D", "max_return_5d": -3.0},
    ]
    assert count_dropped_survivorship(enriched) == 2


def test_count_dropped_survivorship_zero_when_all_valid():
    from backtest_early_signal import count_dropped_survivorship
    enriched = [
        {"ticker": "A", "max_return_5d": 1.0},
        {"ticker": "B", "max_return_5d": 0.0},
    ]
    assert count_dropped_survivorship(enriched) == 0


# ---------------------------------------------------------------------------
# render_report — 추가 필드 (surge_sheet_hit_rate, dropped_count, period_warning)
# ---------------------------------------------------------------------------

def test_render_report_includes_surge_sheet_hit_rate_and_dropped_count():
    from backtest_early_signal import render_report

    horizon_summary = {
        1: {"count": 10, "median": 1.0, "q25": 0.0, "q75": 2.0, "win_rate": 0.5},
    }
    md = render_report(
        title="리포트",
        period=("2026-01-01", "2026-04-17"),
        signal_count=10,
        horizon_summary=horizon_summary,
        surge_threshold=15.0,
        surge_hit_rate=0.3,
        surge_sheet_hit_rate=0.2,
        dropped_count=3,
        sector_table={},
        notes={"entry_price": "신호일 종가", "survivorship": "n/a"},
    )
    # 급등주 시트 매칭 비율과 survivorship 드랍 카운트가 본문에 포함
    assert "20.00%" in md or "20.0%" in md
    assert "3" in md
    assert "급등주" in md or "시트" in md


def test_render_report_includes_period_warning_when_present():
    from backtest_early_signal import render_report
    md = render_report(
        title="리포트",
        period=("2026-04-10", "2026-04-20"),
        signal_count=5,
        horizon_summary={1: {"count": 5, "median": 0.0, "q25": 0.0, "q75": 0.0, "win_rate": 0.0}},
        surge_threshold=15.0,
        surge_hit_rate=0.0,
        surge_sheet_hit_rate=0.0,
        dropped_count=0,
        sector_table={},
        notes={"entry_price": "n/a", "survivorship": "n/a"},
        period_warning="기간이 1개월보다 짧아 통계 신뢰도가 낮습니다.",
    )
    assert "1개월" in md or "신뢰도" in md


# ---------------------------------------------------------------------------
# CLI — 조건 필터 인자 (AC-3)
# ---------------------------------------------------------------------------

def test_build_cli_parser_accepts_signal_condition_filters():
    from backtest_early_signal import build_cli_parser
    parser = build_cli_parser()
    args = parser.parse_args([
        "--start", "2026-01-01",
        "--end", "2026-04-17",
        "--min-change", "5",
        "--max-change", "29.5",
        "--min-rvol", "2.0",
        "--min-streak", "3",
        "--min-52w-ratio", "0.9",
    ])
    assert float(args.min_change) == 5.0
    assert float(args.max_change) == 29.5
    assert float(args.min_rvol) == 2.0
    assert int(args.min_streak) == 3
    assert float(args.min_52w_ratio) == 0.9


def test_build_cli_parser_help_renders_with_percent_literals():
    """argparse help 문자열의 리터럴 % 때문에 --help 가 깨지지 않아야 한다."""
    from backtest_early_signal import build_cli_parser
    parser = build_cli_parser()
    try:
        parser.parse_args(["--help"])
        assert False, "--help should exit after rendering help"
    except SystemExit as exc:
        assert exc.code == 0


def test_build_cli_parser_min_period_days_override():
    from backtest_early_signal import build_cli_parser
    parser = build_cli_parser()
    args = parser.parse_args([
        "--start", "2026-04-01", "--end", "2026-04-10",
        "--min-period-days", "5",
    ])
    assert int(args.min_period_days) == 5


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_compute_horizon_returns_basic()
    test_compute_horizon_returns_missing_data_returns_none()
    test_compute_horizon_returns_zero_base_returns_none()
    test_summarize_returns_basic_quartiles()
    test_summarize_returns_empty_input()
    test_summarize_returns_drops_none()
    test_summarize_returns_all_losses_zero_win_rate()
    test_compute_surge_hit_rate_basic()
    test_compute_surge_hit_rate_empty()
    test_compute_surge_hit_rate_skips_none_max()
    test_compute_sector_hit_rate_basic()
    test_compute_sector_hit_rate_skips_unknown_sector()
    test_load_early_signals_filters_by_date_range()
    test_load_early_signals_skips_blank_or_invalid_rows()
    test_render_report_contains_required_sections()
    test_render_report_handles_empty_signals()
    test_build_cli_parser_accepts_period_and_horizons()
    test_build_cli_parser_optional_sector_filter()
    test_build_cli_parser_defaults_horizons()
    test_parse_horizons_csv()
    test_enrich_signals_with_returns_adds_horizons_and_max()
    test_enrich_signals_with_returns_max_none_when_all_missing()
    # --- 추가: 검증 AI FAIL 대응 ---
    test_validate_period_rejects_end_before_start()
    test_validate_period_rejects_shorter_than_min_days()
    test_validate_period_accepts_exactly_min_days()
    test_validate_period_custom_min_days()
    test_apply_signal_filters_min_change()
    test_apply_signal_filters_max_change()
    test_apply_signal_filters_rvol_streak_52w_combined()
    test_apply_signal_filters_empty_returns_input()
    test_compute_max_return_over_window_picks_intermediate_peak()
    test_compute_max_return_over_window_all_missing_returns_none()
    test_compute_max_return_over_window_zero_base_returns_none()
    test_enrich_signals_with_returns_uses_window_scan_for_max()
    test_compute_surge_sheet_hit_rate_matches_actual_entries()
    test_compute_surge_sheet_hit_rate_normalizes_kr_ticker_zfill()
    test_compute_surge_sheet_hit_rate_normalizes_us_ticker_upper()
    test_compute_surge_sheet_hit_rate_empty_entries_zero()
    test_compute_surge_sheet_hit_rate_no_double_count_same_ticker()
    test_count_dropped_survivorship_counts_none_max()
    test_count_dropped_survivorship_zero_when_all_valid()
    test_render_report_includes_surge_sheet_hit_rate_and_dropped_count()
    test_render_report_includes_period_warning_when_present()
    test_build_cli_parser_accepts_signal_condition_filters()
    test_build_cli_parser_help_renders_with_percent_literals()
    test_build_cli_parser_min_period_days_override()
    print("[PASS] test_backtest_early_signal 전체 통과")
