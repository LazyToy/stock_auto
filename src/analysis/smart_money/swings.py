"""스윙 프랙탈 및 시장구조 탐지

PR-02: 캔들 고점/저점 기반 스윙 하이, 스윙 로우를 탐지하고
최근 구조가 상승/하락/중립인지 계산합니다.

설계 원칙:
    - 순수 탐지 함수만 포함한다. 네트워크, Streamlit, LLM 의존성 없음.
    - 모든 함수는 동일 입력에 동일 출력을 보장한다 (deterministic).
    - 데이터 부족 또는 컬럼 누락 시 빈 결과를 반환하며, 예외를 던지지 않는다.
    - None 등 잘못된 입력에는 명시적 ValueError를 발생시킨다.
    - detect_structure_breaks는 각 bar 시점의 확정 과거 스윙만으로 구조를 판단한다
      (lookahead bias 없음).

수정 이력:
    v1.1 — 리뷰 기반 수정
        [Critical] classify_market_structure: 전체 히스토리 단조성 대신
                   최근 2개 스윙 pair 기준으로 판정하여 "최근 구조" 반영.
        [Critical] detect_structure_breaks: 함수 진입 시 전체 swings로 계산한
                   초기 current_structure를 제거. 이제 각 bar 시점에서
                   bar_index < i인 과거 스윙만으로 구조를 계산한다.
        [Major]    detect_structure_breaks: 'close' 컬럼 누락 검증 추가.
        [Major]    detect_swing_points / detect_structure_breaks:
                   DatetimeIndex 검증 추가 → non-DatetimeIndex에서 AttributeError 방지.
        [Major]    detect_structure_breaks: used_swing_indices 키를 int → (SwingType, int)
                   튜플로 변경 → 같은 bar의 HIGH/LOW가 서로 차단하는 버그 수정.
        [Minor]    모듈 docstring의 warnings 반환 계약 설명을 실제 동작에 맞게 수정.
"""

from __future__ import annotations

import logging
from typing import cast

import pandas as pd

from src.analysis.smart_money.models import (
    BreakDirection,
    BreakType,
    MarketStructure,
    StructureBreak,
    SwingPoint,
    SwingType,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 상수
# ────────────────────────────────────────────────────────────

# 기본 left/right window 크기 (스윙 탐지)
DEFAULT_LEFT: int = 2
DEFAULT_RIGHT: int = 2

# 시장구조 판단을 위한 최소 스윙 포인트 수
MIN_SWINGS_FOR_STRUCTURE: int = 3

# classify_market_structure에서 참조하는 최근 스윙 pair 수
# 최근 N개 HIGH pair와 최근 N개 LOW pair를 보고 구조를 판정한다.
RECENT_SWING_PAIRS: int = 2

# detect_structure_breaks에서 사용할 필수 컬럼 목록
_REQUIRED_BREAK_COLUMNS: tuple[str, ...] = ("high", "low", "close")


# ────────────────────────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────────────────────────


def detect_swing_points(
    df: pd.DataFrame,
    left: int = DEFAULT_LEFT,
    right: int = DEFAULT_RIGHT,
) -> list[SwingPoint]:
    """OHLCV DataFrame에서 확정된 스윙 하이 / 스윙 로우를 탐지합니다.

    스윙 규칙:
        swing_high: 현재 high가 좌우 left/right개 캔들 high보다 크거나 같고,
                    최소 한쪽은 엄격히 크다.
        swing_low:  현재 low가 좌우 left/right개 캔들 low보다 작거나 같고,
                    최소 한쪽은 엄격히 작다.
        마지막 right개 캔들은 확정 전이므로 탐지 대상에서 제외한다.

    Args:
        df: 표준 OHLCV DataFrame (DatetimeIndex, ohlcv 소문자 컬럼).
            normalize_ohlcv_frame()을 먼저 통과한 데이터를 권장합니다.
        left:  현재 캔들 왼쪽으로 비교할 캔들 수 (최소 1 이상)
        right: 현재 캔들 오른쪽으로 비교할 캔들 수 (최소 1 이상)

    Returns:
        탐지된 SwingPoint 리스트 (시간 오름차순).
        데이터가 left + right + 1 미만이면 빈 리스트를 반환합니다.

    Raises:
        ValueError: df가 None이거나 DatetimeIndex가 아닌 경우,
                    left 또는 right가 1 미만인 경우
    """
    # ── None 검증 ──────────────────────────────────────────
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")

    # ── DatetimeIndex 검증 ─────────────────────────────────
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. " "normalize_ohlcv_frame()을 먼저 호출하세요."
        )

    # ── left / right 범위 검증 ─────────────────────────────
    if left < 1:
        raise ValueError(f"left는 1 이상이어야 합니다. 현재 값: {left}")
    if right < 1:
        raise ValueError(f"right는 1 이상이어야 합니다. 현재 값: {right}")

    min_required = left + right + 1
    if len(df) < min_required:
        logger.debug("데이터 부족으로 스윙 탐지 불가: rows=%d, 필요=%d", len(df), min_required)
        return []

    if "high" not in df.columns or "low" not in df.columns:
        logger.warning("'high' 또는 'low' 컬럼이 없어 스윙을 탐지할 수 없습니다.")
        return []

    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    # 마지막 right개 캔들은 확정 전이므로 탐지 제외
    last_confirmable = n - right

    swings: list[SwingPoint] = []

    for i in range(left, last_confirmable):
        left_highs = highs[i - left : i]
        right_highs = highs[i + 1 : i + right + 1]
        cur_high = highs[i]

        # 스윙 하이: 현재 high >= 모든 주변, 최소 한쪽은 엄격히 크다
        left_ok_h = all(cur_high >= h for h in left_highs)
        right_ok_h = all(cur_high >= h for h in right_highs)
        strict_left_h = any(cur_high > h for h in left_highs)
        strict_right_h = any(cur_high > h for h in right_highs)

        if left_ok_h and right_ok_h and (strict_left_h or strict_right_h):
            swings.append(
                SwingPoint(
                    timestamp=cast(pd.Timestamp, df.index[i]).to_pydatetime(),
                    price=float(cur_high),
                    swing_type=SwingType.HIGH,
                    bar_index=i,
                )
            )

        left_lows = lows[i - left : i]
        right_lows = lows[i + 1 : i + right + 1]
        cur_low = lows[i]

        # 스윙 로우: 현재 low <= 모든 주변, 최소 한쪽은 엄격히 작다
        left_ok_l = all(cur_low <= lo for lo in left_lows)
        right_ok_l = all(cur_low <= lo for lo in right_lows)
        strict_left_l = any(cur_low < lo for lo in left_lows)
        strict_right_l = any(cur_low < lo for lo in right_lows)

        if left_ok_l and right_ok_l and (strict_left_l or strict_right_l):
            swings.append(
                SwingPoint(
                    timestamp=cast(pd.Timestamp, df.index[i]).to_pydatetime(),
                    price=float(cur_low),
                    swing_type=SwingType.LOW,
                    bar_index=i,
                )
            )

    # 시간 오름차순으로 정렬
    swings.sort(key=lambda s: s.timestamp)
    return swings


def classify_market_structure(swings: list[SwingPoint]) -> MarketStructure:
    """탐지된 스윙 포인트로 시장 구조를 분류합니다.

    분류 규칙 (최근 구조 기준):
        최근 RECENT_SWING_PAIRS(기본 2)개의 swing high pair와
        swing low pair를 보고 구조를 판정합니다.
        전체 히스토리가 아닌 최근 구조만 반영하여 구조 전환을 빠르게 포착합니다.

        BULLISH: 최근 스윙 하이가 상승(HH)하고 최근 스윙 로우가 상승(HL)하면
        BEARISH: 최근 스윙 하이가 하락(LH)하고 최근 스윙 로우가 하락(LL)하면
        RANGE:   위 조건이 혼재하거나 스윙 포인트가 MIN_SWINGS_FOR_STRUCTURE 미만이면

    Args:
        swings: detect_swing_points()가 반환한 SwingPoint 리스트 (시간 오름차순)
                None을 전달하면 ValueError가 발생합니다.

    Returns:
        MarketStructure enum 값

    Raises:
        ValueError: swings가 None인 경우
    """
    if swings is None:
        raise ValueError("swings가 None입니다. 빈 리스트([])를 전달하세요.")

    if len(swings) < MIN_SWINGS_FOR_STRUCTURE:
        return MarketStructure.RANGE

    highs = [s for s in swings if s.swing_type == SwingType.HIGH]
    lows = [s for s in swings if s.swing_type == SwingType.LOW]

    # ── [수정] 최근 RECENT_SWING_PAIRS개 pair만 참조 ─────────
    # 전체 히스토리 단조성 대신 최근 구조를 기준으로 판정한다.
    # 예: 10개 스윙 중 9개가 상승이어도 마지막 2개 pair가 하락이면 BEARISH.
    recent_highs = highs[-RECENT_SWING_PAIRS:] if len(highs) >= RECENT_SWING_PAIRS else highs
    recent_lows = lows[-RECENT_SWING_PAIRS:] if len(lows) >= RECENT_SWING_PAIRS else lows

    hh = _is_sequence_ascending(recent_highs)  # Higher High
    hl = _is_sequence_ascending(recent_lows)  # Higher Low
    lh = _is_sequence_descending(recent_highs)  # Lower High
    ll = _is_sequence_descending(recent_lows)  # Lower Low

    if hh and hl:
        return MarketStructure.BULLISH
    if lh and ll:
        return MarketStructure.BEARISH
    return MarketStructure.RANGE


def detect_structure_breaks(
    df: pd.DataFrame,
    swings: list[SwingPoint],
) -> list[StructureBreak]:
    """확정된 스윙 돌파 기준으로 BOS / CHOCH를 탐지합니다.

    탐지 원칙:
        - 확정 스윙 하이 돌파(close > swing_high.price) → Bullish 방향 돌파
        - 확정 스윙 로우 이탈(close < swing_low.price) → Bearish 방향 돌파
        - BOS vs CHOCH 판단 (lookahead bias 없음):
            각 bar 시점에서 bar_index < i인 과거 스윙만으로 현재 구조를 계산한다.
            현재 구조와 동일 방향이면 BOS(추세 지속),
            반대 방향이면 CHOCH(추세 전환).
        - 이미 돌파된 레벨은 (SwingType, bar_index) 단위로 추적하여 재사용하지 않는다.
            → 같은 bar에 HIGH/LOW가 공존해도 서로 차단하지 않는다.

    Args:
        df: 표준 OHLCV DataFrame (DatetimeIndex, ohlcv 소문자 컬럼).
            None을 전달하면 ValueError가 발생합니다.
        swings: detect_swing_points()가 반환한 SwingPoint 리스트 (시간 오름차순).
                None을 전달하면 ValueError가 발생합니다.

    Returns:
        탐지된 StructureBreak 리스트 (시간 오름차순).
        스윙이 없거나 데이터가 부족하면 빈 리스트를 반환합니다.

    Raises:
        ValueError: df 또는 swings가 None인 경우,
                    df의 인덱스가 DatetimeIndex가 아닌 경우
    """
    # ── None 검증 ──────────────────────────────────────────
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")
    if swings is None:
        raise ValueError("swings가 None입니다. 빈 리스트([])를 전달하세요.")

    # ── DatetimeIndex 검증 ─────────────────────────────────
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. " "normalize_ohlcv_frame()을 먼저 호출하세요."
        )

    if not swings or len(df) == 0:
        return []

    # ── 필수 컬럼 검증 (close 포함) ────────────────────────
    missing = [c for c in _REQUIRED_BREAK_COLUMNS if c not in df.columns]
    if missing:
        logger.warning(
            "필수 컬럼 누락으로 구조 돌파를 탐지할 수 없습니다: %s",
            ", ".join(missing),
        )
        return []

    closes = df["close"].values

    # 활성 스윙 레벨 분류
    active_swing_highs: list[SwingPoint] = [s for s in swings if s.swing_type == SwingType.HIGH]
    active_swing_lows: list[SwingPoint] = [s for s in swings if s.swing_type == SwingType.LOW]

    breaks: list[StructureBreak] = []

    # ── [수정] used key: (SwingType, bar_index) 튜플 ──────
    # int 단일 키를 사용하면 같은 bar에 HIGH/LOW가 모두 있을 때
    # 먼저 처리된 타입이 다른 타입의 돌파를 차단하는 버그가 발생한다.
    used_swing_keys: set[tuple[SwingType, int]] = set()

    n = len(df)

    for i in range(n):
        bar_time = cast(pd.Timestamp, df.index[i]).to_pydatetime()
        cur_close = float(closes[i])

        # ── [수정] bar 시점 기준 과거 스윙만으로 현재 구조 계산 ──
        # 함수 진입 시 전체 swings로 계산하면 미래 스윙이 초기 구조에
        # 영향을 주는 lookahead bias가 발생한다.
        past_swings = [s for s in swings if s.bar_index < i]
        current_structure = classify_market_structure(past_swings)

        # 스윙 하이 상방 돌파 검사
        for sw in active_swing_highs:
            if sw.bar_index >= i:
                continue  # 미래 또는 현재 bar 스윙은 건너뜀
            key = (sw.swing_type, sw.bar_index)
            if key in used_swing_keys:
                continue  # 이미 돌파된 레벨 재사용 금지
            if cur_close > sw.price:
                if current_structure == MarketStructure.BEARISH:
                    btype = BreakType.CHOCH  # 하락 구조에서 상방 돌파 → 전환
                else:
                    btype = BreakType.BOS  # 상승/박스에서 상방 돌파 → 지속
                breaks.append(
                    StructureBreak(
                        timestamp=bar_time,
                        break_type=btype,
                        direction=BreakDirection.BULLISH,
                        broken_level=sw.price,
                        bar_index=i,
                    )
                )
                used_swing_keys.add(key)

        # 스윙 로우 하방 이탈 검사
        for sw in active_swing_lows:
            if sw.bar_index >= i:
                continue
            key = (sw.swing_type, sw.bar_index)
            if key in used_swing_keys:
                continue
            if cur_close < sw.price:
                if current_structure == MarketStructure.BULLISH:
                    btype = BreakType.CHOCH  # 상승 구조에서 하방 이탈 → 전환
                else:
                    btype = BreakType.BOS  # 하락/박스에서 하방 이탈 → 지속
                breaks.append(
                    StructureBreak(
                        timestamp=bar_time,
                        break_type=btype,
                        direction=BreakDirection.BEARISH,
                        broken_level=sw.price,
                        bar_index=i,
                    )
                )
                used_swing_keys.add(key)

    breaks.sort(key=lambda b: b.timestamp)
    return breaks


# ────────────────────────────────────────────────────────────
# 내부 헬퍼
# ────────────────────────────────────────────────────────────


def _is_sequence_ascending(swings: list[SwingPoint]) -> bool:
    """스윙 포인트 가격이 연속 상승하는지 확인합니다.

    단조 증가(strictly increasing) 여부를 반환합니다.
    스윙이 2개 미만이면 False를 반환합니다.
    """
    if len(swings) < 2:
        return False
    return all(swings[i].price > swings[i - 1].price for i in range(1, len(swings)))


def _is_sequence_descending(swings: list[SwingPoint]) -> bool:
    """스윙 포인트 가격이 연속 하락하는지 확인합니다.

    단조 감소(strictly decreasing) 여부를 반환합니다.
    스윙이 2개 미만이면 False를 반환합니다.
    """
    if len(swings) < 2:
        return False
    return all(swings[i].price < swings[i - 1].price for i in range(1, len(swings)))
