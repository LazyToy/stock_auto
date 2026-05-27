"""캔들 오더블록 탐지.

PR-04: 구조 돌파 직전 마지막 반대색 캔들을 캔들 오더블록 후보로 탐지하고,
구조 돌파 이후 가격 반응 상태를 추적한다.

설계 원칙:
    - 구조 돌파는 PR-02의 StructureBreak 결과를 입력으로 받는다.
    - PR-04 범위에서는 BOS만 오더블록 생성 기준으로 사용한다.
    - zone은 보수적으로 후보 캔들의 전체 range인 [low, high]를 사용한다.
    - 상태 갱신은 오더블록 후보 캔들이 아니라 BOS 확정 이후 캔들부터 수행한다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

import pandas as pd

from src.analysis.smart_money.models import (
    BreakDirection,
    BreakType,
    OrderBlock,
    OrderBlockDirection,
    OrderBlockStatus,
    StructureBreak,
    SwingPoint,
)

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK: int = 10
BASE_STRENGTH: float = 1.0
VOLUME_STRENGTH_BONUS: float = 0.25
VOLUME_LOOKBACK: int = 20

_REQUIRED_DETECT_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")
_REQUIRED_STATUS_COLUMNS: tuple[str, ...] = ("high", "low")


def detect_order_blocks(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    breaks: list[StructureBreak],
    lookback: int = DEFAULT_LOOKBACK,
) -> list[OrderBlock]:
    """구조 돌파 직전 반대색 캔들 기반 캔들 오더블록을 탐지한다.

    Bullish BOS는 직전 lookback 구간의 마지막 음봉을 bullish OB로 본다.
    Bearish BOS는 직전 lookback 구간의 마지막 양봉을 bearish OB로 본다.

    Args:
        df: 표준 OHLCV DataFrame. DatetimeIndex와 open/high/low/close 컬럼이 필요하다.
        swings: PR-02 스윙 목록. PR-04에서는 인터페이스 호환을 위해 검증만 수행한다.
        breaks: PR-02 구조 돌파 목록.
        lookback: BOS 직전 후보 캔들을 찾을 최대 캔들 수. 1 이상이어야 한다.

    Returns:
        탐지된 OrderBlock 목록. 필수 컬럼 누락, 후보 부재, BOS 부재 시 빈 리스트를 반환한다.

    Raises:
        ValueError: df, swings, breaks가 None이거나 DatetimeIndex가 아니거나 lookback이 1 미만인 경우.
    """
    _validate_dataframe(df)
    if swings is None:
        raise ValueError("swings가 None입니다. 빈 리스트([])를 전달하세요.")
    if breaks is None:
        raise ValueError("breaks가 None입니다. 빈 리스트([])를 전달하세요.")
    if lookback < 1:
        raise ValueError(f"lookback은 1 이상이어야 합니다. 현재 값: {lookback}")

    if len(df) == 0 or not breaks:
        return []

    missing = [column for column in _REQUIRED_DETECT_COLUMNS if column not in df.columns]
    if missing:
        logger.warning(
            "필수 컬럼 누락으로 오더블록을 탐지할 수 없습니다: %s",
            ", ".join(missing),
        )
        return []

    order_blocks: list[OrderBlock] = []
    seen: set[tuple[OrderBlockDirection, int, int, datetime]] = set()

    sorted_breaks = sorted(breaks, key=lambda item: (item.bar_index, item.timestamp))
    for structure_break in sorted_breaks:
        _validate_structure_break(df, structure_break)
        candidate_index = _find_candidate_candle_index(df, structure_break, lookback)
        if candidate_index is None:
            continue

        direction = _to_order_block_direction(structure_break.direction)
        seen_key = (
            direction,
            candidate_index,
            structure_break.bar_index,
            structure_break.timestamp,
        )
        if seen_key in seen:
            continue

        seen.add(seen_key)
        order_blocks.append(_build_order_block(df, structure_break, candidate_index, direction))

    order_blocks.sort(key=lambda item: item.created_at)
    return order_blocks


def update_order_block_status(
    df: pd.DataFrame,
    order_blocks: list[OrderBlock],
) -> list[OrderBlock]:
    """오더블록 목록의 상태를 최신 OHLCV 데이터로 갱신한다.

    상태 갱신은 각 오더블록의 break_at 이후 캔들만 사용한다.
    full DataFrame은 break_bar_index + 1부터, break 이후 future-only DataFrame은 첫 행부터
    스캔해 같은 결과를 내야 한다.

    Args:
        df: 표준 OHLCV DataFrame. DatetimeIndex와 high/low 컬럼이 필요하다.
        order_blocks: detect_order_blocks()가 반환한 OrderBlock 목록.

    Returns:
        상태가 갱신된 OrderBlock 목록. 필수 컬럼 누락 시 원본 목록을 그대로 반환한다.

    Raises:
        ValueError: df 또는 order_blocks가 None이거나 DatetimeIndex가 아닌 경우.
    """
    _validate_dataframe(df)
    if order_blocks is None:
        raise ValueError("order_blocks가 None입니다. 빈 리스트([])를 전달하세요.")

    if not order_blocks or len(df) == 0:
        return list(order_blocks)

    missing = [column for column in _REQUIRED_STATUS_COLUMNS if column not in df.columns]
    if missing:
        logger.warning(
            "필수 컬럼 누락으로 오더블록 상태를 갱신할 수 없습니다: %s",
            ", ".join(missing),
        )
        return list(order_blocks)

    updated: list[OrderBlock] = []
    for order_block in order_blocks:
        _validate_order_block(df, order_block)
        new_status = _scan_status_after_break(df, order_block)
        updated.append(_copy_with_status(order_block, new_status))

    return updated


def _validate_dataframe(df: pd.DataFrame) -> None:
    """공통 DataFrame 입력 조건을 검증한다."""
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달하세요.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. normalize_ohlcv_frame()을 먼저 호출하세요."
        )


def _validate_structure_break(df: pd.DataFrame, structure_break: StructureBreak) -> None:
    """StructureBreak의 bar_index와 timestamp가 같은 캔들을 가리키는지 검증한다."""
    if structure_break.bar_index < 0 or structure_break.bar_index >= len(df):
        return

    expected_timestamp = _timestamp_at(df, structure_break.bar_index)
    if expected_timestamp != structure_break.timestamp:
        raise ValueError(
            "StructureBreak의 timestamp와 bar_index가 서로 다른 캔들을 가리킵니다. "
            "break timestamp를 df.index[bar_index]와 일치시키세요."
        )


def _validate_order_block(df: pd.DataFrame, order_block: OrderBlock) -> None:
    """OrderBlock의 break 시점 정보가 현재 DataFrame과 양립 가능한지 검증한다."""
    if order_block.break_bar_index < 0:
        raise ValueError("OrderBlock.break_bar_index는 0 이상이어야 합니다.")

    if len(df) == 0:
        return

    if _is_future_only_frame(df, order_block.break_at):
        return

    if order_block.break_bar_index < len(df):
        expected_timestamp = _timestamp_at(df, order_block.break_bar_index)
        if expected_timestamp != order_block.break_at:
            raise ValueError(
                "OrderBlock.break_at과 break_bar_index가 현재 DataFrame과 일치하지 않습니다."
            )
        return

    first_timestamp = _timestamp_at(df, 0)
    if first_timestamp <= order_block.break_at:
        raise ValueError(
            "현재 DataFrame이 break 이전 구간을 포함하지만 break_bar_index를 검증할 수 없습니다."
        )


def _find_candidate_candle_index(
    df: pd.DataFrame,
    structure_break: StructureBreak,
    lookback: int,
) -> int | None:
    """구조 돌파 직전 lookback 구간에서 마지막 반대색 캔들의 위치를 찾는다."""
    if structure_break.break_type != BreakType.BOS:
        return None
    if structure_break.bar_index <= 0 or structure_break.bar_index >= len(df):
        return None

    start_index = max(0, structure_break.bar_index - lookback)
    for index in range(structure_break.bar_index - 1, start_index - 1, -1):
        open_price = float(df["open"].iloc[index])
        close_price = float(df["close"].iloc[index])
        if _is_opposite_candle(open_price, close_price, structure_break.direction):
            return index

    return None


def _is_opposite_candle(
    open_price: float,
    close_price: float,
    break_direction: BreakDirection,
) -> bool:
    """구조 돌파 방향과 반대색인 캔들인지 확인한다."""
    if break_direction == BreakDirection.BULLISH:
        return close_price < open_price
    return close_price > open_price


def _to_order_block_direction(break_direction: BreakDirection) -> OrderBlockDirection:
    """구조 돌파 방향을 오더블록 방향으로 변환한다."""
    if break_direction == BreakDirection.BULLISH:
        return OrderBlockDirection.BULLISH
    return OrderBlockDirection.BEARISH


def _build_order_block(
    df: pd.DataFrame,
    structure_break: StructureBreak,
    candidate_index: int,
    direction: OrderBlockDirection,
) -> OrderBlock:
    """후보 캔들과 구조 돌파 정보로 OrderBlock 인스턴스를 만든다."""
    lower = float(df["low"].iloc[candidate_index])
    upper = float(df["high"].iloc[candidate_index])
    if lower > upper:
        lower, upper = upper, lower

    return OrderBlock(
        direction=direction,
        lower=lower,
        upper=upper,
        created_at=cast(pd.Timestamp, df.index[candidate_index]).to_pydatetime(),
        bar_index=candidate_index,
        break_at=_timestamp_at(df, structure_break.bar_index),
        break_bar_index=structure_break.bar_index,
        status=OrderBlockStatus.FRESH,
        strength=_calculate_strength(df, structure_break.bar_index),
    )


def _calculate_strength(df: pd.DataFrame, break_bar_index: int) -> float:
    """BOS 캔들 거래량이 직전 평균 이상이면 강도 점수를 가산한다."""
    if "volume" not in df.columns:
        return BASE_STRENGTH
    if break_bar_index <= 0 or break_bar_index >= len(df):
        return BASE_STRENGTH

    current_volume = float(df["volume"].iloc[break_bar_index])
    if pd.isna(current_volume) or current_volume <= 0:
        return BASE_STRENGTH

    start_index = max(0, break_bar_index - VOLUME_LOOKBACK)
    recent_volume = df["volume"].iloc[start_index:break_bar_index]
    if len(recent_volume) == 0:
        return BASE_STRENGTH

    average_volume = float(recent_volume.mean())
    if pd.isna(average_volume) or average_volume <= 0:
        return BASE_STRENGTH
    if current_volume >= average_volume:
        return BASE_STRENGTH + VOLUME_STRENGTH_BONUS
    return BASE_STRENGTH


def _scan_status_after_break(df: pd.DataFrame, order_block: OrderBlock) -> OrderBlockStatus:
    """BOS 확정 이후 캔들을 순서대로 확인해 최종 상태를 계산한다."""
    new_status = order_block.status
    highs = df["high"].values
    lows = df["low"].values
    start_index = _resolve_scan_start_index(df, order_block)

    for index in range(start_index, len(df)):
        if new_status == OrderBlockStatus.INVALIDATED:
            break

        new_status = _next_status(
            order_block=order_block,
            current_status=new_status,
            high=float(highs[index]),
            low=float(lows[index]),
        )

    return new_status


def _next_status(
    order_block: OrderBlock,
    current_status: OrderBlockStatus,
    high: float,
    low: float,
) -> OrderBlockStatus:
    """단일 캔들이 오더블록 상태에 주는 영향을 계산한다."""
    if order_block.direction == OrderBlockDirection.BULLISH:
        if low < order_block.lower:
            return OrderBlockStatus.INVALIDATED
    elif high > order_block.upper:
        return OrderBlockStatus.INVALIDATED

    if current_status == OrderBlockStatus.FRESH and _touches_zone(order_block, high, low):
        return OrderBlockStatus.MITIGATED
    return current_status


def _touches_zone(order_block: OrderBlock, high: float, low: float) -> bool:
    """캔들 range가 오더블록 zone과 겹치는지 확인한다."""
    return low <= order_block.upper and high >= order_block.lower


def _resolve_scan_start_index(df: pd.DataFrame, order_block: OrderBlock) -> int:
    """full DataFrame과 future-only DataFrame 모두에서 상태 스캔 시작 지점을 계산한다."""
    if len(df) == 0:
        return 0

    if _is_future_only_frame(df, order_block.break_at):
        return 0

    if order_block.break_bar_index < len(df):
        return order_block.break_bar_index + 1

    for index in range(len(df)):
        if _timestamp_at(df, index) > order_block.break_at:
            return index
    return len(df)


def _is_future_only_frame(df: pd.DataFrame, break_at: datetime) -> bool:
    """현재 DataFrame이 break 이후 구간만 담고 있는지 판별한다."""
    return len(df) > 0 and _timestamp_at(df, 0) > break_at


def _timestamp_at(df: pd.DataFrame, index: int) -> datetime:
    """DataFrame의 특정 위치 timestamp를 Python datetime으로 반환한다."""
    return cast(pd.Timestamp, df.index[index]).to_pydatetime()


def _copy_with_status(order_block: OrderBlock, status: OrderBlockStatus) -> OrderBlock:
    """frozen OrderBlock을 새 상태로 복사한다."""
    if status == order_block.status:
        return order_block

    return OrderBlock(
        direction=order_block.direction,
        lower=order_block.lower,
        upper=order_block.upper,
        created_at=order_block.created_at,
        bar_index=order_block.bar_index,
        break_at=order_block.break_at,
        break_bar_index=order_block.break_bar_index,
        status=status,
        strength=order_block.strength,
    )
