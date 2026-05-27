"""Fair Value Gap (FVG) 탐지

PR-03: 3-캔들 불균형 기반 FVG를 탐지하고,
최근 가격이 gap에 진입/완전 메움/미메움 상태인지 계산합니다.

설계 원칙:
    - 순수 탐지 함수만 포함한다. 네트워크, Streamlit, LLM 의존성 없음.
    - 모든 함수는 동일 입력에 동일 출력을 보장한다 (deterministic).
    - 데이터 부족 또는 컬럼 누락 시 빈 결과를 반환하며, 예외를 던지지 않는다.
    - None 등 잘못된 입력에는 명시적 ValueError를 발생시킨다.
    - FVG는 lookahead bias 없이 형성된 시점(bar i) 기준으로 탐지한다.

FVG 정의:
    Bullish FVG: 캔들 i-2의 high < 캔들 i의 low
        → gap 범위: [high[i-2], low[i]]
    Bearish FVG: 캔들 i-2의 low > 캔들 i의 high
        → gap 범위: [high[i], low[i-2]]

필터:
    gap_size / close[i] >= min_gap_pct (기본 0.1%)
"""

from __future__ import annotations

import logging
from typing import cast

import pandas as pd

from src.analysis.smart_money.models import (
    FairValueGap,
    FVGDirection,
    FVGStatus,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 상수
# ────────────────────────────────────────────────────────────

# FVG 탐지에 필요한 최소 캔들 수 (i-2, i-1, i 세 캔들 필요)
MIN_CANDLES_FOR_FVG: int = 3

# 기본 최소 갭 크기 비율 (close 대비)
DEFAULT_MIN_GAP_PCT: float = 0.001  # 0.1%

# detect_fvgs에서 사용하는 필수 컬럼
_REQUIRED_FVG_COLUMNS: tuple[str, ...] = ("high", "low", "close")

# update_fvg_status에서 사용하는 필수 컬럼
_REQUIRED_STATUS_COLUMNS: tuple[str, ...] = ("high", "low")


# ────────────────────────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────────────────────────


def detect_fvgs(
    df: pd.DataFrame,
    min_gap_pct: float = DEFAULT_MIN_GAP_PCT,
) -> list[FairValueGap]:
    """OHLCV DataFrame에서 Fair Value Gap(FVG)을 탐지합니다.

    3개 연속 캔들(i-2, i-1, i)에서 캔들 i-2와 캔들 i 사이에
    겹치지 않는 가격 구간이 있으면 FVG로 탐지합니다.

    탐지 규칙:
        Bullish FVG: high[i-2] < low[i]
            gap 범위: [high[i-2], low[i]]
        Bearish FVG: low[i-2] > high[i]
            gap 범위: [high[i], low[i-2]]

    필터:
        gap_size / close[i] >= min_gap_pct 를 만족하는 FVG만 반환한다.
        (기본값 0.001 = 0.1%)

    Args:
        df: 표준 OHLCV DataFrame (DatetimeIndex, ohlcv 소문자 컬럼).
            normalize_ohlcv_frame()을 먼저 통과한 데이터를 권장합니다.
        min_gap_pct: 유효 FVG 최소 크기 비율 (close[i] 대비). 기본 0.001.

    Returns:
        탐지된 FairValueGap 리스트 (시간 오름차순, status=OPEN).
        데이터가 3개 미만이면 빈 리스트를 반환합니다.

    Raises:
        ValueError: df가 None이거나 DatetimeIndex가 아닌 경우,
                    min_gap_pct가 0 미만인 경우
    """
    # ── None 검증 ──────────────────────────────────────────
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")

    # ── DatetimeIndex 검증 ─────────────────────────────────
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. " "normalize_ohlcv_frame()을 먼저 호출하세요."
        )

    # ── min_gap_pct 범위 검증 ──────────────────────────────
    if min_gap_pct < 0:
        raise ValueError(f"min_gap_pct는 0 이상이어야 합니다. 현재 값: {min_gap_pct}")

    # ── 최소 캔들 수 검증 ──────────────────────────────────
    if len(df) < MIN_CANDLES_FOR_FVG:
        logger.debug(
            "데이터 부족으로 FVG 탐지 불가: rows=%d, 필요=%d",
            len(df),
            MIN_CANDLES_FOR_FVG,
        )
        return []

    # ── 필수 컬럼 검증 ─────────────────────────────────────
    missing = [c for c in _REQUIRED_FVG_COLUMNS if c not in df.columns]
    if missing:
        logger.warning(
            "필수 컬럼 누락으로 FVG를 탐지할 수 없습니다: %s",
            ", ".join(missing),
        )
        return []

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    fvgs: list[FairValueGap] = []

    # i=2부터 탐지 (i-2, i-1, i 세 캔들이 모두 필요)
    for i in range(2, n):
        h_prev2 = float(highs[i - 2])  # 캔들 i-2 의 high
        l_prev2 = float(lows[i - 2])  # 캔들 i-2 의 low
        h_cur = float(highs[i])  # 캔들 i 의 high
        l_cur = float(lows[i])  # 캔들 i 의 low
        c_cur = float(closes[i])  # 캔들 i 의 close (필터 기준)

        bar_time = cast(pd.Timestamp, df.index[i]).to_pydatetime()

        # ── Bullish FVG ────────────────────────────────────
        # 조건: 캔들 i-2 의 high < 캔들 i 의 low
        if h_prev2 < l_cur:
            gap_lower = h_prev2
            gap_upper = l_cur
            gap_size = gap_upper - gap_lower

            # close가 0이거나 음수인 경우 division-by-zero 방지
            if c_cur > 0 and (gap_size / c_cur) >= min_gap_pct:
                fvgs.append(
                    FairValueGap(
                        direction=FVGDirection.BULLISH,
                        lower=gap_lower,
                        upper=gap_upper,
                        created_at=bar_time,
                        bar_index=i,
                        status=FVGStatus.OPEN,
                    )
                )

        # ── Bearish FVG ────────────────────────────────────
        # 조건: 캔들 i-2 의 low > 캔들 i 의 high
        if l_prev2 > h_cur:
            gap_lower = h_cur
            gap_upper = l_prev2
            gap_size = gap_upper - gap_lower

            if c_cur > 0 and (gap_size / c_cur) >= min_gap_pct:
                fvgs.append(
                    FairValueGap(
                        direction=FVGDirection.BEARISH,
                        lower=gap_lower,
                        upper=gap_upper,
                        created_at=bar_time,
                        bar_index=i,
                        status=FVGStatus.OPEN,
                    )
                )

    # 시간 오름차순 정렬 (bar_index 기준이 timestamp와 일치)
    fvgs.sort(key=lambda f: f.created_at)
    return fvgs


def update_fvg_status(
    df: pd.DataFrame,
    fvgs: list[FairValueGap],
) -> list[FairValueGap]:
    """탐지된 FVG 목록에 대해 최신 가격 데이터로 상태를 업데이트합니다.

    각 FVG에 대해 fvg.created_at보다 이후 timestamp인 캔들을 순서대로 확인하며
    가장 마지막으로 도달한 상태로 업데이트합니다.

    상태 전환 규칙:
        OPEN → TOUCHED: 캔들의 low(Bullish) 또는 high(Bearish)가 gap 범위에 진입
        TOUCHED → FILLED: 캔들의 low(Bullish)가 gap_lower 이하 또는
                          캔들의 high(Bearish)가 gap_upper 이상

    주의:
        - 스캔 기준은 df의 위치(bar_index)가 아니라 fvg.created_at timestamp이다.
          따라서 df가 full DataFrame이든 FVG 이후 슬라이스든 동일하게 동작한다.
        - FILLED는 최종 상태이므로 이후 캔들에서 다시 변경하지 않는다.
        - TOUCHED 이후에도 gap 범위를 완전히 메우지 않으면 TOUCHED를 유지한다.
        - fvg.created_at과 timestamp가 동일한 캔들(형성 캔들)은 제외한다.

    Args:
        df: 표준 OHLCV DataFrame (DatetimeIndex, ohlcv 소문자 컬럼).
            full DataFrame 또는 FVG 형성 이후 캔들 슬라이스 모두 사용 가능.
        fvgs: detect_fvgs()가 반환한 FairValueGap 리스트.
              None을 전달하면 ValueError가 발생합니다.

    Returns:
        상태가 업데이트된 FairValueGap 리스트 (원본 순서 유지).
        fvgs가 비어있으면 빈 리스트를 반환합니다.

    Raises:
        ValueError: df 또는 fvgs가 None인 경우,
                    df의 인덱스가 DatetimeIndex가 아닌 경우
    """
    # ── None 검증 ──────────────────────────────────────────
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")
    if fvgs is None:
        raise ValueError("fvgs가 None입니다. 빈 리스트([])를 전달하세요.")

    # ── DatetimeIndex 검증 ─────────────────────────────────
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. " "normalize_ohlcv_frame()을 먼저 호출하세요."
        )

    if not fvgs or len(df) == 0:
        return list(fvgs)

    # ── 필수 컬럼 검증 ─────────────────────────────────────
    missing = [c for c in _REQUIRED_STATUS_COLUMNS if c not in df.columns]
    if missing:
        logger.warning(
            "필수 컬럼 누락으로 FVG 상태를 업데이트할 수 없습니다: %s",
            ", ".join(missing),
        )
        return list(fvgs)

    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    updated: list[FairValueGap] = []

    for fvg in fvgs:
        new_status = fvg.status

        # ── [수정] timestamp 기준 스캔 ─────────────────────
        # bar_index 위치 기반 대신 created_at 이후 timestamp인 캔들만 확인한다.
        # 이로써 full DataFrame / future-only 슬라이스 모두 동일하게 동작한다.
        for i in range(n):
            bar_ts = cast(pd.Timestamp, df.index[i]).to_pydatetime()
            if bar_ts <= fvg.created_at:
                continue  # FVG 형성 캔들 및 그 이전은 제외
            if new_status == FVGStatus.FILLED:
                break  # FILLED는 최종 상태

            h = float(highs[i])
            lo = float(lows[i])

            if fvg.direction == FVGDirection.BULLISH:
                # Bullish FVG: gap = [lower, upper]
                # FILLED: low가 gap_lower 이하 (gap을 완전히 통과)
                # TOUCHED: low가 gap 범위 안으로 진입 (lower <= low <= upper)
                if lo <= fvg.lower:
                    new_status = FVGStatus.FILLED
                elif lo <= fvg.upper and new_status == FVGStatus.OPEN:
                    new_status = FVGStatus.TOUCHED

            else:
                # Bearish FVG: gap = [lower, upper]
                # FILLED: high가 gap_upper 이상 (gap을 완전히 통과)
                # TOUCHED: high가 gap 범위 안으로 진입 (lower <= high <= upper)
                if h >= fvg.upper:
                    new_status = FVGStatus.FILLED
                elif h >= fvg.lower and new_status == FVGStatus.OPEN:
                    new_status = FVGStatus.TOUCHED

        # frozen dataclass이므로 새 인스턴스로 교체
        if new_status != fvg.status:
            updated.append(
                FairValueGap(
                    direction=fvg.direction,
                    lower=fvg.lower,
                    upper=fvg.upper,
                    created_at=fvg.created_at,
                    bar_index=fvg.bar_index,
                    status=new_status,
                )
            )
        else:
            updated.append(fvg)

    return updated
