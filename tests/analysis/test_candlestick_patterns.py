"""PR-05 캔들 패턴 탐지 테스트

검증 항목:
    - bullish_engulfing 탐지
    - bearish_engulfing 탐지
    - hammer와 shooting_star 구분
    - doji body 비율 경계값
    - gap candle에서 range==0 ZeroDivisionError 방지
    - 데이터 1개만 있어도 단일 캔들 패턴 탐지 가능
    - None / 비-DatetimeIndex 입력 ValueError
    - 필수 컬럼 누락 시 빈 리스트
    - strength 범위 [0.0, 1.0]
    - 결과가 bar_index 오름차순
"""

import pandas as pd
import pytest

from src.analysis.candlestick_patterns import (
    DEFAULT_DOJI_BODY_RATIO,
    DEFAULT_STRONG_BODY_RATIO,
    DEFAULT_WICK_BODY_RATIO,
    CandleDirection,
    CandlePattern,
    detect_candlestick_patterns,
)

# ─────────────────────────────────────────────────────────────
# 픽스처 헬퍼
# ─────────────────────────────────────────────────────────────


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """OHLCV 딕셔너리 리스트를 DatetimeIndex DataFrame으로 변환한다."""
    idx = pd.date_range("2024-01-02", periods=len(rows), freq="5min")
    df = pd.DataFrame(rows, index=idx)
    return df


def _single(name: str, patterns: list[CandlePattern]) -> CandlePattern:
    """특정 이름의 패턴이 정확히 1개인지 확인 후 반환한다."""
    found = [p for p in patterns if p.name == name]
    assert len(found) == 1, f"패턴 '{name}'이 {len(found)}개 탐지됨 (기대: 1)"
    return found[0]


# ─────────────────────────────────────────────────────────────
# 1. 입력 검증 테스트
# ─────────────────────────────────────────────────────────────


class TestInputValidation:
    """None / 비-DatetimeIndex / 필수 컬럼 누락 검증"""

    def test_none_df_raises_value_error(self) -> None:
        """df=None이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="None"):
            detect_candlestick_patterns(None)  # type: ignore[arg-type]

    def test_non_datetime_index_raises_value_error(self) -> None:
        """DatetimeIndex가 아닌 인덱스는 ValueError가 발생해야 한다."""
        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5]},
            index=[0],
        )
        with pytest.raises(ValueError, match="DatetimeIndex"):
            detect_candlestick_patterns(df)

    def test_missing_columns_returns_empty(self) -> None:
        """필수 컬럼이 없으면 빈 리스트를 반환해야 한다."""
        idx = pd.date_range("2024-01-02", periods=3, freq="5min")
        df = pd.DataFrame({"open": [1.0, 2.0, 3.0], "close": [1.5, 2.5, 3.5]}, index=idx)
        result = detect_candlestick_patterns(df)
        assert result == []

    def test_empty_df_returns_empty(self) -> None:
        """빈 DataFrame이면 빈 리스트를 반환해야 한다."""
        idx = pd.DatetimeIndex([])
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []}, index=idx)
        result = detect_candlestick_patterns(df)
        assert result == []


# ─────────────────────────────────────────────────────────────
# 2. Bullish Engulfing
# ─────────────────────────────────────────────────────────────


class TestBullishEngulfing:
    """상승 장악형 패턴 탐지"""

    def test_basic_bullish_engulfing(self) -> None:
        """이전 음봉을 완전히 감싸는 양봉이 bullish_engulfing으로 탐지되어야 한다."""
        df = _make_df(
            [
                # 이전: 음봉 (open=110, close=100)
                {"open": 110.0, "high": 112.0, "low": 98.0, "close": 100.0},
                # 현재: 양봉, 이전 음봉 완전 장악 (open<=100, close>=110)
                {"open": 99.0, "high": 115.0, "low": 97.0, "close": 111.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        p = _single("bullish_engulfing", patterns)
        assert p.direction == CandleDirection.BULLISH
        assert p.bar_index == 1
        assert 0.0 < p.strength <= 1.0

    def test_no_engulfing_when_not_fully_covered(self) -> None:
        """현재 close가 이전 open에 미치지 못하면 engulfing이 아니다."""
        df = _make_df(
            [
                {"open": 110.0, "high": 112.0, "low": 98.0, "close": 100.0},
                # close=108: 이전 open=110 미달
                {"open": 99.0, "high": 112.0, "low": 97.0, "close": 108.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        engulf = [p for p in patterns if p.name == "bullish_engulfing"]
        assert len(engulf) == 0

    def test_both_bullish_no_engulfing(self) -> None:
        """두 캔들 모두 양봉이면 bullish engulfing이 없어야 한다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 110.0, "low": 99.0, "close": 108.0},
                {"open": 99.0, "high": 115.0, "low": 97.0, "close": 112.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        engulf = [p for p in patterns if p.name == "bullish_engulfing"]
        assert len(engulf) == 0


# ─────────────────────────────────────────────────────────────
# 3. Bearish Engulfing
# ─────────────────────────────────────────────────────────────


class TestBearishEngulfing:
    """하락 장악형 패턴 탐지"""

    def test_basic_bearish_engulfing(self) -> None:
        """이전 양봉을 완전히 감싸는 음봉이 bearish_engulfing으로 탐지되어야 한다."""
        df = _make_df(
            [
                # 이전: 양봉 (open=100, close=110)
                {"open": 100.0, "high": 112.0, "low": 98.0, "close": 110.0},
                # 현재: 음봉, 이전 양봉 완전 장악 (open>=110, close<=100)
                {"open": 111.0, "high": 114.0, "low": 97.0, "close": 99.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        p = _single("bearish_engulfing", patterns)
        assert p.direction == CandleDirection.BEARISH
        assert p.bar_index == 1
        assert 0.0 < p.strength <= 1.0

    def test_no_engulfing_when_not_fully_covered(self) -> None:
        """현재 close가 이전 open보다 높으면 engulfing이 아니다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 112.0, "low": 98.0, "close": 110.0},
                # close=102: 이전 open=100 초과
                {"open": 111.0, "high": 114.0, "low": 100.0, "close": 102.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        engulf = [p for p in patterns if p.name == "bearish_engulfing"]
        assert len(engulf) == 0


# ─────────────────────────────────────────────────────────────
# 4. Hammer & Shooting Star
# ─────────────────────────────────────────────────────────────


class TestHammerAndShootingStar:
    """망치형과 유성형 구분"""

    def test_hammer_detected(self) -> None:
        """아래꼬리가 몸통의 2배 이상이고 위꼬리가 작으면 hammer여야 한다."""
        # 몸통: 100→102 (크기 2), 아래꼬리: 100-95=5 (>= 2*2=4), 위꼬리: 102.5-102=0.5 (<2)
        df = _make_df([{"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0}])
        patterns = detect_candlestick_patterns(df)
        p = _single("hammer", patterns)
        assert p.direction == CandleDirection.BULLISH

    def test_shooting_star_detected(self) -> None:
        """위꼬리가 몸통의 2배 이상이고 아래꼬리가 작으면 shooting_star여야 한다."""
        # 몸통: 108→106 (크기 2), 위꼬리: 113-108=5 (>=2*2=4), 아래꼬리: 106-105.5=0.5 (<2)
        df = _make_df([{"open": 108.0, "high": 113.0, "low": 105.5, "close": 106.0}])
        patterns = detect_candlestick_patterns(df)
        p = _single("shooting_star", patterns)
        assert p.direction == CandleDirection.BEARISH

    def test_hammer_and_shooting_star_are_exclusive(self) -> None:
        """같은 캔들에서 hammer와 shooting_star가 동시에 탐지되지 않아야 한다."""
        # 대칭 캔들 — 위/아래 꼬리가 같은 경우 → 어느 쪽도 탐지 안 됨
        df = _make_df([{"open": 105.0, "high": 110.0, "low": 100.0, "close": 105.0}])
        patterns = detect_candlestick_patterns(df)
        hammer = [p for p in patterns if p.name == "hammer"]
        star = [p for p in patterns if p.name == "shooting_star"]
        assert not (len(hammer) > 0 and len(star) > 0)

    def test_single_candle_returns_pattern(self) -> None:
        """캔들이 1개뿐이어도 단일 캔들 패턴은 탐지 가능해야 한다."""
        df = _make_df([{"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0}])
        patterns = detect_candlestick_patterns(df)
        assert len(patterns) >= 1


# ─────────────────────────────────────────────────────────────
# 5. Doji
# ─────────────────────────────────────────────────────────────


class TestDoji:
    """도지 body 비율 경계값 테스트"""

    def test_doji_at_boundary(self) -> None:
        """몸통/range == DOJI_BODY_RATIO 경계에서 doji가 탐지되어야 한다."""
        # range=10, body=1 → body_ratio=0.1 == DEFAULT_DOJI_BODY_RATIO
        df = _make_df([{"open": 100.0, "high": 105.0, "low": 95.0, "close": 101.0}])
        patterns = detect_candlestick_patterns(df)
        doji_list = [p for p in patterns if p.name == "doji"]
        assert len(doji_list) == 1
        assert doji_list[0].direction == CandleDirection.NEUTRAL

    def test_non_doji_above_threshold(self) -> None:
        """몸통/range > DOJI_BODY_RATIO 이면 doji가 아니어야 한다."""
        # range=10, body=5 → body_ratio=0.5
        df = _make_df([{"open": 100.0, "high": 105.0, "low": 95.0, "close": 105.0}])
        patterns = detect_candlestick_patterns(df)
        doji_list = [p for p in patterns if p.name == "doji"]
        assert len(doji_list) == 0

    def test_doji_strength_is_clamped(self) -> None:
        """doji strength는 [0.0, 1.0] 범위여야 한다."""
        df = _make_df([{"open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0}])
        patterns = detect_candlestick_patterns(df)
        for p in patterns:
            assert 0.0 <= p.strength <= 1.0


# ─────────────────────────────────────────────────────────────
# 6. Strong Candle
# ─────────────────────────────────────────────────────────────


class TestStrongCandle:
    """강한 양봉/음봉 탐지"""

    def test_strong_bullish_detected(self) -> None:
        """몸통/range >= strong_body_ratio이고 양봉이면 strong_bullish여야 한다."""
        # open=91, close=99 → 양봉, range=high(100)-low(90)=10, body=8 → body_ratio=0.8 >= 0.7
        # upper_wick=100-99=1 < body(8), lower_wick=91-90=1 < body(8) → hammer/star 아님
        df = _make_df([{"open": 91.0, "high": 100.0, "low": 90.0, "close": 99.0}])
        patterns = detect_candlestick_patterns(df, strong_body_ratio=DEFAULT_STRONG_BODY_RATIO)
        sb = [p for p in patterns if p.name == "strong_bullish"]
        assert len(sb) == 1
        assert sb[0].direction == CandleDirection.BULLISH

    def test_strong_bearish_detected(self) -> None:
        """몸통/range >= strong_body_ratio이고 음봉이면 strong_bearish여야 한다."""
        # range=10, body=8 → body_ratio=0.8 >= 0.7
        df = _make_df([{"open": 99.0, "high": 100.0, "low": 90.0, "close": 91.0}])
        patterns = detect_candlestick_patterns(df, strong_body_ratio=DEFAULT_STRONG_BODY_RATIO)
        sb = [p for p in patterns if p.name == "strong_bearish"]
        assert len(sb) == 1
        assert sb[0].direction == CandleDirection.BEARISH

    def test_weak_candle_not_strong(self) -> None:
        """몸통/range < strong_body_ratio이면 strong 패턴이 없어야 한다."""
        # range=10, body=4 → body_ratio=0.4 < 0.7
        df = _make_df([{"open": 100.0, "high": 104.0, "low": 94.0, "close": 104.0}])
        patterns = detect_candlestick_patterns(df)
        strong = [p for p in patterns if "strong" in p.name]
        assert len(strong) == 0


# ─────────────────────────────────────────────────────────────
# 7. Gap Candle (range == 0)
# ─────────────────────────────────────────────────────────────


class TestGapCandle:
    """range == 0인 갭 캔들에서 ZeroDivisionError 방지"""

    def test_gap_candle_no_error(self) -> None:
        """open==high==low==close인 캔들에서 예외 없이 처리되어야 한다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
                {"open": 105.0, "high": 110.0, "low": 103.0, "close": 108.0},
            ]
        )
        result = detect_candlestick_patterns(df)
        # 갭 캔들 자체는 range==0이므로 패턴 없음
        gap_patterns = [p for p in result if p.bar_index == 0]
        assert len(gap_patterns) == 0

    def test_mixed_gap_and_normal_candles(self) -> None:
        """갭 캔들이 섞여도 정상 캔들의 패턴은 탐지되어야 한다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},  # 갭
                {"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0},  # hammer
            ]
        )
        result = detect_candlestick_patterns(df)
        bar1_patterns = [p for p in result if p.bar_index == 1]
        assert len(bar1_patterns) >= 1


# ─────────────────────────────────────────────────────────────
# 8. 결과 순서 & 일반 속성
# ─────────────────────────────────────────────────────────────


class TestResultProperties:
    """결과 순서, strength 범위, CandlePattern 속성 검증"""

    def test_results_sorted_by_bar_index(self) -> None:
        """결과 리스트는 bar_index 오름차순이어야 한다."""
        df = _make_df(
            [
                # bar 0: hammer
                {"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0},
                # bar 1: bearish (이전 양봉을 감쌈 → bearish_engulfing)
                {"open": 103.0, "high": 105.0, "low": 94.0, "close": 99.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        indices = [p.bar_index for p in patterns]
        assert indices == sorted(indices)

    def test_strength_always_in_range(self) -> None:
        """모든 패턴의 strength는 [0.0, 1.0] 범위여야 한다."""
        df = _make_df(
            [
                {"open": 110.0, "high": 112.0, "low": 98.0, "close": 100.0},
                {"open": 99.0, "high": 115.0, "low": 97.0, "close": 111.0},
                {"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0},
                {"open": 108.0, "high": 113.0, "low": 105.5, "close": 106.0},
                {"open": 105.0, "high": 105.2, "low": 104.8, "close": 105.1},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        for p in patterns:
            assert 0.0 <= p.strength <= 1.0, f"strength 범위 초과: {p}"

    def test_pattern_has_required_fields(self) -> None:
        """CandlePattern 인스턴스가 필수 필드를 모두 갖고 있어야 한다."""
        df = _make_df([{"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0}])
        patterns = detect_candlestick_patterns(df)
        assert len(patterns) >= 1
        p = patterns[0]
        assert isinstance(p, CandlePattern)
        assert isinstance(p.name, str)
        assert isinstance(p.direction, CandleDirection)
        assert p.bar_index >= 0
        assert 0.0 <= p.strength <= 1.0

    def test_single_candle_only_single_patterns(self) -> None:
        """캔들이 1개이면 2-캔들 패턴(engulfing)은 탐지되지 않아야 한다."""
        df = _make_df([{"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0}])
        patterns = detect_candlestick_patterns(df)
        engulf = [p for p in patterns if "engulfing" in p.name]
        assert len(engulf) == 0


# ─────────────────────────────────────────────────────────────
# 9. 커스텀 임계값 파라미터
# ─────────────────────────────────────────────────────────────


class TestCustomThresholds:
    """doji_body_ratio, wick_body_ratio, strong_body_ratio 커스텀 동작 확인"""

    def test_stricter_doji_ratio(self) -> None:
        """doji_body_ratio를 매우 작게 설정하면 도지가 탐지되지 않아야 한다."""
        # range=10, body=1 → body_ratio=0.1; 임계값=0.05 이면 도지 아님
        df = _make_df([{"open": 100.0, "high": 105.0, "low": 95.0, "close": 101.0}])
        patterns = detect_candlestick_patterns(df, doji_body_ratio=0.05)
        doji_list = [p for p in patterns if p.name == "doji"]
        assert len(doji_list) == 0

    def test_looser_doji_ratio(self) -> None:
        """doji_body_ratio를 크게 설정하면 body_ratio=0.3인 캔들도 도지로 탐지된다."""
        # range=10, body=3 → body_ratio=0.3; 임계값=0.4 이면 도지
        df = _make_df([{"open": 100.0, "high": 105.0, "low": 95.0, "close": 103.0}])
        patterns = detect_candlestick_patterns(df, doji_body_ratio=0.4)
        doji_list = [p for p in patterns if p.name == "doji"]
        assert len(doji_list) == 1

    def test_custom_strong_body_ratio(self) -> None:
        """strong_body_ratio=0.5로 낮추면 body_ratio=0.6인 캔들도 strong으로 탐지된다."""
        # open=94, close=100 → 양봉, range=high(101)-low(94)=7, body=6 → body_ratio≈0.857 >= 0.5
        # upper_wick=101-100=1 < body(6), lower_wick=94-94=0 < body(6)
        df = _make_df([{"open": 94.0, "high": 101.0, "low": 94.0, "close": 100.0}])
        patterns = detect_candlestick_patterns(df, strong_body_ratio=0.5)
        strong = [p for p in patterns if "strong" in p.name]
        assert len(strong) == 1


# ─────────────────────────────────────────────────────────────
# 10. threshold 범위 검증 — ValueError 발생 여부 (Issue #1, #4)
# ─────────────────────────────────────────────────────────────


class TestThresholdValidation:
    """음수/범위 초과 threshold 입력 시 ValueError 발생 확인"""

    def _base_df(self) -> pd.DataFrame:
        return _make_df([{"open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0}])

    # ── doji_body_ratio ──────────────────────────────────────

    def test_negative_doji_body_ratio_raises(self) -> None:
        """doji_body_ratio < 0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="doji_body_ratio"):
            detect_candlestick_patterns(self._base_df(), doji_body_ratio=-0.1)

    def test_doji_body_ratio_above_one_raises(self) -> None:
        """doji_body_ratio > 1.0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="doji_body_ratio"):
            detect_candlestick_patterns(self._base_df(), doji_body_ratio=1.1)

    def test_doji_body_ratio_zero_is_valid(self) -> None:
        """doji_body_ratio == 0.0은 경계값이므로 예외 없이 처리되어야 한다."""
        result = detect_candlestick_patterns(self._base_df(), doji_body_ratio=0.0)
        assert isinstance(result, list)

    def test_doji_body_ratio_one_is_valid(self) -> None:
        """doji_body_ratio == 1.0은 경계값이므로 예외 없이 처리되어야 한다."""
        result = detect_candlestick_patterns(self._base_df(), doji_body_ratio=1.0)
        assert isinstance(result, list)

    # ── wick_body_ratio ──────────────────────────────────────

    def test_negative_wick_body_ratio_raises(self) -> None:
        """wick_body_ratio < 0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="wick_body_ratio"):
            detect_candlestick_patterns(self._base_df(), wick_body_ratio=-1.0)

    def test_wick_body_ratio_zero_is_valid(self) -> None:
        """wick_body_ratio == 0.0은 경계값이므로 예외 없이 처리되어야 한다."""
        result = detect_candlestick_patterns(self._base_df(), wick_body_ratio=0.0)
        assert isinstance(result, list)

    # ── strong_body_ratio ────────────────────────────────────

    def test_negative_strong_body_ratio_raises(self) -> None:
        """strong_body_ratio < 0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="strong_body_ratio"):
            detect_candlestick_patterns(self._base_df(), strong_body_ratio=-0.1)

    def test_strong_body_ratio_above_one_raises(self) -> None:
        """strong_body_ratio > 1.0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="strong_body_ratio"):
            detect_candlestick_patterns(self._base_df(), strong_body_ratio=1.5)


# ─────────────────────────────────────────────────────────────
# 11. wick_body_ratio 커스텀 동작 (Issue #4)
# ─────────────────────────────────────────────────────────────


class TestWickBodyRatioCustom:
    """wick_body_ratio 커스텀 값에 따른 hammer / shooting_star 탐지 동작 확인"""

    def test_strict_wick_ratio_suppresses_hammer(self) -> None:
        """wick_body_ratio를 크게 설정하면 기존 hammer가 탐지되지 않아야 한다."""
        # lower_wick=5, body=2 → ratio=2.5; 임계값=10이면 조건 미달 → hammer 없음
        df = _make_df([{"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0}])
        patterns = detect_candlestick_patterns(df, wick_body_ratio=10.0)
        hammer = [p for p in patterns if p.name == "hammer"]
        assert len(hammer) == 0

    def test_loose_wick_ratio_detects_hammer(self) -> None:
        """wick_body_ratio를 낮게 설정하면 이전에 탐지 안 되던 캔들도 hammer가 된다."""
        # lower_wick=2, body=3 → default ratio(2배) 조건 미달이지만 ratio=0.5면 충족
        # open=100, close=103(양봉), high=103.5, low=98
        # body=3, lower_wick=min(100,103)-98=2, upper_wick=103.5-103=0.5
        # 2 >= 3*0.5=1.5 이고 upper_wick(0.5) < body(3) → hammer
        df = _make_df([{"open": 100.0, "high": 103.5, "low": 98.0, "close": 103.0}])
        patterns = detect_candlestick_patterns(df, wick_body_ratio=0.5)
        hammer = [p for p in patterns if p.name == "hammer"]
        assert len(hammer) == 1


# ─────────────────────────────────────────────────────────────
# 12. timestamp 정확성 검증 (Issue #5)
# ─────────────────────────────────────────────────────────────


class TestTimestampAccuracy:
    """CandlePattern.timestamp가 DataFrame 인덱스 시각과 정확히 일치하는지 검증"""

    def test_single_candle_timestamp_matches_index(self) -> None:
        """단일 캔들 패턴의 timestamp가 해당 행 DatetimeIndex 값과 일치해야 한다."""
        df = _make_df([{"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0}])
        patterns = detect_candlestick_patterns(df)
        assert len(patterns) >= 1
        expected_ts = df.index[0].to_pydatetime()
        for p in patterns:
            assert (
                p.timestamp == expected_ts
            ), f"패턴 '{p.name}'의 timestamp({p.timestamp}) ≠ 인덱스({expected_ts})"

    def test_double_candle_timestamp_matches_second_bar(self) -> None:
        """engulfing 패턴의 timestamp는 두 번째 캔들(bar_index=1)의 시각이어야 한다."""
        df = _make_df(
            [
                {"open": 110.0, "high": 112.0, "low": 98.0, "close": 100.0},
                {"open": 99.0, "high": 115.0, "low": 97.0, "close": 111.0},
            ]
        )
        patterns = detect_candlestick_patterns(df)
        engulf = [p for p in patterns if p.name == "bullish_engulfing"]
        assert len(engulf) == 1
        expected_ts = df.index[1].to_pydatetime()
        assert engulf[0].timestamp == expected_ts

    def test_multiple_candles_timestamps_are_ordered(self) -> None:
        """여러 캔들에서 탐지된 패턴의 timestamp는 bar_index 오름차순과 일치해야 한다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 102.5, "low": 95.0, "close": 102.0},  # bar 0
                {"open": 110.0, "high": 112.0, "low": 98.0, "close": 100.0},  # bar 1
                {"open": 99.0, "high": 115.0, "low": 97.0, "close": 111.0},  # bar 2
            ]
        )
        patterns = detect_candlestick_patterns(df)
        for p in patterns:
            expected = df.index[p.bar_index].to_pydatetime()
            assert (
                p.timestamp == expected
            ), f"bar_index={p.bar_index}의 timestamp({p.timestamp}) ≠ 인덱스({expected})"
