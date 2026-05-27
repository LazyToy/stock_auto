"""캔들 패턴 탐지 (Candlestick Pattern Detection)

PR-05: 진입/청산 타이밍 보조에 사용할 기본 캔들 패턴을 탐지합니다.

설계 원칙:
    - 순수 탐지 함수만 포함한다. 네트워크, Streamlit, LLM 의존성 없음.
    - 모든 함수는 동일 입력에 동일 출력을 보장한다 (deterministic).
    - ta-lib, pandas-ta 등 외부 캔들 라이브러리를 사용하지 않는다.
    - 모든 임계값은 상수 또는 함수 인자로 제공한다.
    - range == 0(갭 캔들)에서 ZeroDivisionError가 발생하지 않도록 방어한다.
    - None 또는 DatetimeIndex가 아닌 입력은 ValueError로 즉시 거부한다.
    - 데이터 부족은 빈 리스트를 반환한다.

지원 패턴 (PR-05 범위):
    - bullish_engulfing  : 상승 장악 (2-캔들)
    - bearish_engulfing  : 하락 장악 (2-캔들)
    - hammer             : 망치형 (단일)
    - shooting_star      : 유성형 (단일)
    - doji               : 도지 (단일, neutral)
    - strong_bullish     : 강한 양봉 (단일)
    - strong_bearish     : 강한 음봉 (단일)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import cast

import pandas as pd

logger = logging.getLogger(__name__)


# ── Enum ─────────────────────────────────────────────────────


class CandleDirection(str, Enum):
    """캔들 패턴의 방향성"""

    BULLISH = "BULLISH"  # 상승 신호
    BEARISH = "BEARISH"  # 하락 신호
    NEUTRAL = "NEUTRAL"  # 방향 불확실


# ── Dataclass ────────────────────────────────────────────────


@dataclass(frozen=True)
class CandlePattern:
    """탐지된 캔들 패턴 결과

    Attributes:
        name      : 패턴 이름 (예: "bullish_engulfing")
        direction : 방향성 (BULLISH / BEARISH / NEUTRAL)
        timestamp : 패턴이 확정된 캔들의 시각 (마지막 캔들 기준)
        bar_index : DataFrame 내 위치 인덱스 (0-based)
        strength  : 패턴 강도 (0.0 ~ 1.0)
    """

    name: str
    direction: CandleDirection
    timestamp: datetime
    bar_index: int
    strength: float = 1.0


# ── 임계값 상수 ──────────────────────────────────────────────

# 도지: 몸통/전체범위 비율이 이 값 이하이면 도지로 간주
DEFAULT_DOJI_BODY_RATIO: float = 0.1

# 망치/유성: 꼬리 길이가 몸통의 이 배 이상이어야 패턴 인정
DEFAULT_WICK_BODY_RATIO: float = 2.0

# 강한 캔들: 몸통/전체범위 비율이 이 값 이상이면 강한 캔들로 간주
DEFAULT_STRONG_BODY_RATIO: float = 0.7

_REQUIRED_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")
_MIN_CANDLES_SINGLE: int = 1
_MIN_CANDLES_DOUBLE: int = 2


# ── 내부 헬퍼 ────────────────────────────────────────────────


def _validate_df(df: pd.DataFrame) -> None:
    """공통 입력 검증.

    Raises:
        ValueError: df가 None이거나 DatetimeIndex가 아닌 경우
    """
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. " "normalize_ohlcv_frame()을 먼저 호출하세요."
        )


def _check_columns(df: pd.DataFrame) -> bool:
    """필수 컬럼 존재 여부 검사. 누락 시 False 반환."""
    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        logger.warning(
            "필수 컬럼 누락으로 캔들 패턴을 탐지할 수 없습니다: %s",
            ", ".join(missing),
        )
        return False
    return True


def _clamp(value: float) -> float:
    """strength 값을 [0.0, 1.0] 범위로 제한한다."""
    return max(0.0, min(1.0, value))


def _bar_time(df: pd.DataFrame, idx: int) -> datetime:
    """DataFrame 행 인덱스에서 datetime을 추출한다."""
    return cast(pd.Timestamp, df.index[idx]).to_pydatetime()


# ── 공개 API ─────────────────────────────────────────────────


def _validate_thresholds(
    doji_body_ratio: float,
    wick_body_ratio: float,
    strong_body_ratio: float,
) -> None:
    """threshold 파라미터 범위를 검증한다.

    Raises:
        ValueError: 임계값이 허용 범위를 벗어난 경우
    """
    if not (0.0 <= doji_body_ratio <= 1.0):
        raise ValueError(
            f"doji_body_ratio는 0.0 이상 1.0 이하여야 합니다. 현재 값: {doji_body_ratio}"
        )
    if wick_body_ratio < 0.0:
        raise ValueError(f"wick_body_ratio는 0.0 이상이어야 합니다. 현재 값: {wick_body_ratio}")
    if not (0.0 <= strong_body_ratio <= 1.0):
        raise ValueError(
            f"strong_body_ratio는 0.0 이상 1.0 이하여야 합니다. 현재 값: {strong_body_ratio}"
        )


def detect_candlestick_patterns(
    df: pd.DataFrame,
    doji_body_ratio: float = DEFAULT_DOJI_BODY_RATIO,
    wick_body_ratio: float = DEFAULT_WICK_BODY_RATIO,
    strong_body_ratio: float = DEFAULT_STRONG_BODY_RATIO,
) -> list[CandlePattern]:
    """OHLCV DataFrame에서 캔들 패턴 전체를 탐지합니다.

    단일 캔들 패턴(doji / hammer / shooting_star / strong)은 상호 배타적입니다.
    한 캔들에서는 최우선 조건 하나만 탐지합니다 (doji > hammer > shooting_star > strong).
    2-캔들 패턴(engulfing)은 단일 캔들 패턴과 독립적으로 평가됩니다.
    후속 scoring에서는 최근 3~5개 캔들만 반영하도록 필터링합니다.

    Args:
        df               : 표준 OHLCV DataFrame (DatetimeIndex, ohlcv 소문자 컬럼).
                           normalize_ohlcv_frame()을 먼저 통과한 데이터를 권장합니다.
        doji_body_ratio  : 도지 판정 몸통/range 비율 상한. 0.0~1.0. 기본 0.1.
        wick_body_ratio  : 망치/유성 꼬리 길이 배수 하한. 0.0 이상. 기본 2.0.
        strong_body_ratio: 강한 캔들 몸통/range 비율 하한. 0.0~1.0. 기본 0.7.

    Returns:
        탐지된 CandlePattern 리스트 (bar_index 오름차순).
        캔들이 1개 미만이면 빈 리스트를 반환합니다.

    Raises:
        ValueError: df가 None이거나 DatetimeIndex가 아닌 경우,
                    또는 threshold 값이 허용 범위를 벗어난 경우
    """
    _validate_df(df)
    _validate_thresholds(doji_body_ratio, wick_body_ratio, strong_body_ratio)

    if len(df) < _MIN_CANDLES_SINGLE:
        logger.debug("데이터 부족으로 캔들 패턴 탐지 불가: rows=%d", len(df))
        return []

    if not _check_columns(df):
        return []

    patterns: list[CandlePattern] = []

    # 단일 캔들 패턴 (배타적: 캔들당 최대 1개)
    patterns.extend(
        _detect_single_candle_patterns(df, doji_body_ratio, wick_body_ratio, strong_body_ratio)
    )

    # 2-캔들 패턴 (2개 이상일 때만, 단일 패턴과 독립 평가)
    if len(df) >= _MIN_CANDLES_DOUBLE:
        patterns.extend(_detect_double_candle_patterns(df))

    patterns.sort(key=lambda p: (p.bar_index, p.name))
    return patterns


# ── 내부: 단일 캔들 패턴 ─────────────────────────────────────


def _detect_single_candle_patterns(
    df: pd.DataFrame,
    doji_body_ratio: float,
    wick_body_ratio: float,
    strong_body_ratio: float,
) -> list[CandlePattern]:
    """doji / hammer / shooting_star / strong_bullish / strong_bearish를 탐지한다."""
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    results: list[CandlePattern] = []

    for i in range(n):
        o = float(opens[i])
        h = float(highs[i])
        lo = float(lows[i])
        c = float(closes[i])
        ts = _bar_time(df, i)

        candle_range = h - lo  # 전체 범위
        body = abs(c - o)  # 몸통 크기

        # range == 0 방어 (갭 캔들 등)
        if candle_range <= 0.0:
            continue

        body_ratio = body / candle_range

        # ── Doji ─────────────────────────────────────────────
        if body_ratio <= doji_body_ratio:
            results.append(
                CandlePattern(
                    name="doji",
                    direction=CandleDirection.NEUTRAL,
                    timestamp=ts,
                    bar_index=i,
                    strength=_clamp(1.0 - body_ratio / max(doji_body_ratio, 1e-9)),
                )
            )
            continue  # 도지이면 다른 단일 패턴 탐지 생략

        upper_wick = h - max(o, c)  # 위꼬리
        lower_wick = min(o, c) - lo  # 아래꼬리

        # ── Hammer (망치형) ───────────────────────────────────
        # 아래꼬리 >= 몸통 × wick_body_ratio, 위꼬리 < 몸통
        if lower_wick >= body * wick_body_ratio and upper_wick < body:
            strength = _clamp(lower_wick / (body * wick_body_ratio + 1e-9))
            results.append(
                CandlePattern(
                    name="hammer",
                    direction=CandleDirection.BULLISH,
                    timestamp=ts,
                    bar_index=i,
                    strength=strength,
                )
            )

        # ── Shooting Star (유성형) ────────────────────────────
        # 위꼬리 >= 몸통 × wick_body_ratio, 아래꼬리 < 몸통
        elif upper_wick >= body * wick_body_ratio and lower_wick < body:
            strength = _clamp(upper_wick / (body * wick_body_ratio + 1e-9))
            results.append(
                CandlePattern(
                    name="shooting_star",
                    direction=CandleDirection.BEARISH,
                    timestamp=ts,
                    bar_index=i,
                    strength=strength,
                )
            )

        # ── Strong Bullish (강한 양봉) ────────────────────────
        elif body_ratio >= strong_body_ratio and c > o:
            results.append(
                CandlePattern(
                    name="strong_bullish",
                    direction=CandleDirection.BULLISH,
                    timestamp=ts,
                    bar_index=i,
                    strength=_clamp(body_ratio),
                )
            )

        # ── Strong Bearish (강한 음봉) ─────────────────────────
        elif body_ratio >= strong_body_ratio and c < o:
            results.append(
                CandlePattern(
                    name="strong_bearish",
                    direction=CandleDirection.BEARISH,
                    timestamp=ts,
                    bar_index=i,
                    strength=_clamp(body_ratio),
                )
            )

    return results


# ── 내부: 2-캔들 패턴 ────────────────────────────────────────


def _detect_double_candle_patterns(df: pd.DataFrame) -> list[CandlePattern]:
    """bullish_engulfing / bearish_engulfing을 탐지한다."""
    opens = df["open"].values
    closes = df["close"].values
    n = len(df)

    results: list[CandlePattern] = []

    for i in range(1, n):
        o_prev = float(opens[i - 1])
        c_prev = float(closes[i - 1])
        o_cur = float(opens[i])
        c_cur = float(closes[i])
        ts = _bar_time(df, i)

        prev_body = abs(c_prev - o_prev)
        cur_body = abs(c_cur - o_cur)

        # strength: 현재 몸통 / 이전 몸통 비율 (1.0으로 클램프)
        engulf_strength = _clamp(cur_body / prev_body) if prev_body > 0 else 1.0

        # ── Bullish Engulfing (상승 장악) ─────────────────────
        # 이전: 음봉, 현재: 양봉, 현재가 이전을 완전히 감쌈
        if (
            c_prev < o_prev  # 이전: 음봉
            and c_cur > o_cur  # 현재: 양봉
            and o_cur <= c_prev  # 현재 open <= 이전 close
            and c_cur >= o_prev  # 현재 close >= 이전 open
        ):
            results.append(
                CandlePattern(
                    name="bullish_engulfing",
                    direction=CandleDirection.BULLISH,
                    timestamp=ts,
                    bar_index=i,
                    strength=engulf_strength,
                )
            )

        # ── Bearish Engulfing (하락 장악) ─────────────────────
        # 이전: 양봉, 현재: 음봉, 현재가 이전을 완전히 감쌈
        elif (
            c_prev > o_prev  # 이전: 양봉
            and c_cur < o_cur  # 현재: 음봉
            and o_cur >= c_prev  # 현재 open >= 이전 close
            and c_cur <= o_prev  # 현재 close <= 이전 open
        ):
            results.append(
                CandlePattern(
                    name="bearish_engulfing",
                    direction=CandleDirection.BEARISH,
                    timestamp=ts,
                    bar_index=i,
                    strength=engulf_strength,
                )
            )

    return results
