"""타임프레임별 Smart Money 패턴 리포트.

PR-07: swing/FVG/order block/캔들 패턴 탐지 결과를 timeframe 단위 관찰 리포트로 묶는다.

설계 원칙:
    - 기존 탐지 함수(swings/fvg/order_blocks/candlestick_patterns)를 조합만 한다.
    - BUY/SELL/HOLD 같은 최종 의사결정은 포함하지 않는다.
    - 데이터 부족이나 컬럼 누락은 warning으로 남기고 가능한 범위까지 리포트를 생성한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pandas as pd

from src.analysis.candlestick_patterns import (
    CandleDirection,
    CandlePattern,
    detect_candlestick_patterns,
)
from src.analysis.ohlcv import REQUIRED_COLUMNS as STANDARD_OHLCV_COLUMNS
from src.analysis.ohlcv import (
    normalize_ohlcv_frame,
    validate_ohlcv_frame,
)
from src.analysis.smart_money.fvg import (
    MIN_CANDLES_FOR_FVG,
    detect_fvgs,
    update_fvg_status,
)
from src.analysis.smart_money.liquidity import detect_liquidity_sweeps
from src.analysis.smart_money.models import (
    FairValueGap,
    FVGStatus,
    LiquiditySweep,
    MarketStructure,
    OrderBlock,
    OrderBlockStatus,
    SmartMoneyPatternConfig,
    StructureBreak,
    SwingPoint,
    SwingType,
)
from src.analysis.smart_money.order_blocks import (
    detect_order_blocks,
    update_order_block_status,
)
from src.analysis.smart_money.swings import (
    classify_market_structure,
    detect_structure_breaks,
    detect_swing_points,
)

RECENT_PATTERN_LOOKBACK: int = 5
MIN_CANDLES_FOR_DOUBLE_CANDLE_PATTERN: int = 2

_REQUIRED_SWING_COLUMNS: tuple[str, ...] = ("high", "low")
_REQUIRED_FVG_COLUMNS: tuple[str, ...] = ("high", "low", "close")
_REQUIRED_ORDER_BLOCK_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")
_REQUIRED_PATTERN_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")
_REQUIRED_OHLC_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")


@dataclass(frozen=True)
class PatternSummary:
    """리포트에서 바로 사용할 수 있는 집계 요약."""

    swing_count: int = 0
    structure_break_count: int = 0
    open_fvg_count: int = 0
    touched_fvg_count: int = 0
    filled_fvg_count: int = 0
    fresh_order_block_count: int = 0
    mitigated_order_block_count: int = 0
    invalidated_order_block_count: int = 0
    liquidity_sweep_count: int = 0
    bullish_pattern_count: int = 0
    bearish_pattern_count: int = 0
    neutral_pattern_count: int = 0


@dataclass
class TimeframePatternReport:
    """단일 timeframe의 관찰 리포트."""

    timeframe: str
    latest_close: float | None
    market_structure: MarketStructure
    recent_swing_high: SwingPoint | None
    recent_swing_low: SwingPoint | None
    latest_bar_index: int | None = None
    swings: list[SwingPoint] = field(default_factory=list)
    structure_breaks: list[StructureBreak] = field(default_factory=list)
    open_fvgs: list[FairValueGap] = field(default_factory=list)
    touched_fvgs: list[FairValueGap] = field(default_factory=list)
    filled_fvgs: list[FairValueGap] = field(default_factory=list)
    fresh_order_blocks: list[OrderBlock] = field(default_factory=list)
    mitigated_order_blocks: list[OrderBlock] = field(default_factory=list)
    invalidated_order_blocks: list[OrderBlock] = field(default_factory=list)
    liquidity_sweeps: list[LiquiditySweep] = field(default_factory=list)
    recent_candle_patterns: list[CandlePattern] = field(default_factory=list)
    summary: PatternSummary = field(default_factory=PatternSummary)
    warnings: list[str] = field(default_factory=list)


def analyze_timeframe_patterns(
    df: pd.DataFrame,
    timeframe: str,
    pattern_config: SmartMoneyPatternConfig | None = None,
) -> TimeframePatternReport:
    """단일 OHLCV DataFrame을 정규화/검증 후 timeframe 관찰 리포트로 변환한다."""
    active_config = pattern_config or SmartMoneyPatternConfig()
    normalized_df = _prepare_dataframe(df)

    warnings = _build_warnings(normalized_df, active_config)
    latest_close = _extract_latest_close(normalized_df)

    swings = detect_swing_points(
        normalized_df,
        left=active_config.swing_left,
        right=active_config.swing_right,
    )
    structure = classify_market_structure(swings)
    structure_breaks = detect_structure_breaks(normalized_df, swings)
    structure_breaks = _filter_structure_breaks_by_displacement(
        normalized_df,
        structure_breaks,
        active_config,
    )

    fvgs = update_fvg_status(
        normalized_df,
        detect_fvgs(normalized_df, min_gap_pct=active_config.fvg_min_gap_pct),
    )
    open_fvgs, touched_fvgs, filled_fvgs = _partition_fvgs(fvgs)

    order_blocks = update_order_block_status(
        normalized_df,
        detect_order_blocks(
            normalized_df,
            swings,
            structure_breaks,
            lookback=active_config.order_block_lookback,
        ),
    )
    fresh_order_blocks, mitigated_order_blocks, invalidated_order_blocks = _partition_order_blocks(
        order_blocks
    )
    liquidity_sweeps = detect_liquidity_sweeps(
        normalized_df,
        swings,
        tolerance_pct=active_config.liquidity_sweep_tolerance_pct,
    )

    recent_candle_patterns = _select_recent_patterns(
        normalized_df,
        detect_candlestick_patterns(normalized_df),
    )

    report = TimeframePatternReport(
        timeframe=timeframe,
        latest_close=latest_close,
        latest_bar_index=(len(normalized_df) - 1) if len(normalized_df) > 0 else None,
        market_structure=structure,
        recent_swing_high=_find_recent_swing(swings, SwingType.HIGH),
        recent_swing_low=_find_recent_swing(swings, SwingType.LOW),
        swings=swings,
        structure_breaks=structure_breaks,
        open_fvgs=open_fvgs,
        touched_fvgs=touched_fvgs,
        filled_fvgs=filled_fvgs,
        fresh_order_blocks=fresh_order_blocks,
        mitigated_order_blocks=mitigated_order_blocks,
        invalidated_order_blocks=invalidated_order_blocks,
        liquidity_sweeps=liquidity_sweeps,
        recent_candle_patterns=recent_candle_patterns,
        warnings=warnings,
    )
    report.summary = _build_summary(report)
    return report


def analyze_multi_timeframe_patterns(
    dataset: Mapping[str, pd.DataFrame],
    pattern_config: SmartMoneyPatternConfig | None = None,
) -> dict[str, TimeframePatternReport]:
    """여러 timeframe DataFrame을 각각 리포트로 변환한다."""
    if dataset is None:
        raise ValueError("dataset이 None입니다. timeframe별 OHLCV DataFrame dict를 전달해주세요.")

    reports: dict[str, TimeframePatternReport] = {}
    for timeframe, frame in dataset.items():
        reports[timeframe] = analyze_timeframe_patterns(
            frame,
            timeframe,
            pattern_config=pattern_config,
        )
    return reports


def _validate_dataframe(df: pd.DataFrame) -> None:
    """공통 DataFrame 입력 조건을 검증한다."""
    if df is None:
        raise ValueError("df가 None입니다. 유효한 OHLCV DataFrame을 전달해주세요.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "df의 인덱스가 DatetimeIndex가 아닙니다. normalize_ohlcv_frame()를 먼저 호출해주세요."
        )


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """리포트 입력 DataFrame을 표준 OHLCV 계약에 맞게 정규화하고 검증한다."""
    _validate_dataframe(df)

    normalized_df = normalize_ohlcv_frame(df)
    invalid_numeric_columns = _find_invalid_numeric_columns(normalized_df)
    if invalid_numeric_columns:
        raise ValueError(
            "OHLCV numeric 컬럼에 숫자가 아닌 dtype이 있습니다: "
            + ", ".join(invalid_numeric_columns)
        )

    _validate_ohlc_structure(normalized_df)

    if all(column in normalized_df.columns for column in STANDARD_OHLCV_COLUMNS):
        is_valid, errors = validate_ohlcv_frame(normalized_df)
        blocking_errors = [
            error
            for error in errors
            if error.startswith("invalid_datetime")
            or error.startswith("invalid_dtype")
            or error.startswith("invalid_candle")
        ]
        if not is_valid and blocking_errors:
            raise ValueError("표준 OHLCV 검증에 실패했습니다: " + ", ".join(blocking_errors))

    return normalized_df


def _find_invalid_numeric_columns(df: pd.DataFrame) -> list[str]:
    """존재하는 OHLCV 컬럼 중 numeric dtype이 아닌 컬럼을 찾는다."""
    invalid_columns: list[str] = []
    for column in STANDARD_OHLCV_COLUMNS:
        if column in df.columns and not pd.api.types.is_numeric_dtype(df[column]):
            invalid_columns.append(column)
    return invalid_columns


def _validate_ohlc_structure(df: pd.DataFrame) -> None:
    """open/high/low/close가 있으면 비정상 캔들 구조를 명시적으로 차단한다."""
    if not all(column in df.columns for column in _REQUIRED_OHLC_COLUMNS):
        return

    invalid_mask = (df["high"] < df[["open", "close"]].max(axis=1)) | (
        df["low"] > df[["open", "close"]].min(axis=1)
    )
    invalid_indices = df.index[invalid_mask].tolist()
    if invalid_indices:
        invalid_index_text = ", ".join(str(index) for index in invalid_indices)
        raise ValueError(f"비정상 OHLC 캔들이 있습니다: {invalid_index_text}")


def _build_warnings(
    df: pd.DataFrame,
    pattern_config: SmartMoneyPatternConfig | None = None,
) -> list[str]:
    """데이터 부족/컬럼 누락 경고를 생성한다."""
    warnings: list[str] = []
    active_config = pattern_config or SmartMoneyPatternConfig()

    if len(df) == 0:
        warnings.append("데이터가 비어 있어 패턴 분석 결과가 제한됩니다.")

    swing_min_rows = active_config.swing_left + active_config.swing_right + 1
    if len(df) < swing_min_rows:
        warnings.append(
            f"스윙/구조 분석에 필요한 캔들 수가 부족합니다. 필요={swing_min_rows}, 현재={len(df)}"
        )
    if len(df) < MIN_CANDLES_FOR_FVG:
        warnings.append(
            f"FVG 분석에 필요한 캔들 수가 부족합니다. 필요={MIN_CANDLES_FOR_FVG}, 현재={len(df)}"
        )
    if len(df) < MIN_CANDLES_FOR_DOUBLE_CANDLE_PATTERN:
        warnings.append(
            "2-캔들 패턴 분석에 필요한 캔들 수가 부족합니다. engulfing 패턴은 생략됩니다."
        )

    _append_missing_column_warning(
        warnings,
        df,
        _REQUIRED_SWING_COLUMNS,
        "스윙/구조 분석",
    )
    _append_missing_column_warning(
        warnings,
        df,
        _REQUIRED_FVG_COLUMNS,
        "FVG 분석",
    )
    _append_missing_column_warning(
        warnings,
        df,
        _REQUIRED_ORDER_BLOCK_COLUMNS,
        "오더블록 분석",
    )
    _append_missing_column_warning(
        warnings,
        df,
        _REQUIRED_PATTERN_COLUMNS,
        "캔들 패턴 분석",
    )

    if "close" not in df.columns:
        warnings.append("latest close 계산에 필요한 close 컬럼이 없습니다.")

    return warnings


def _append_missing_column_warning(
    warnings: list[str],
    df: pd.DataFrame,
    required_columns: tuple[str, ...],
    analysis_name: str,
) -> None:
    """컬럼 누락 warning을 추가한다."""
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        warnings.append(f"{analysis_name}에 필요한 컬럼이 부족합니다: {', '.join(missing)}")


def _extract_latest_close(df: pd.DataFrame) -> float | None:
    """마지막 close 값을 반환한다."""
    if len(df) == 0 or "close" not in df.columns:
        return None
    return float(df["close"].iloc[-1])


def _find_recent_swing(swings: list[SwingPoint], swing_type: SwingType) -> SwingPoint | None:
    """가장 최근 swing high/low를 반환한다."""
    filtered = [swing for swing in swings if swing.swing_type == swing_type]
    if not filtered:
        return None
    return filtered[-1]


def _partition_fvgs(
    fvgs: list[FairValueGap],
) -> tuple[list[FairValueGap], list[FairValueGap], list[FairValueGap]]:
    """FVG를 상태별로 분류한다."""
    open_fvgs = [fvg for fvg in fvgs if fvg.status == FVGStatus.OPEN]
    touched_fvgs = [fvg for fvg in fvgs if fvg.status == FVGStatus.TOUCHED]
    filled_fvgs = [fvg for fvg in fvgs if fvg.status == FVGStatus.FILLED]
    return open_fvgs, touched_fvgs, filled_fvgs


def _partition_order_blocks(
    order_blocks: list[OrderBlock],
) -> tuple[list[OrderBlock], list[OrderBlock], list[OrderBlock]]:
    """오더블록을 상태별로 분류한다."""
    fresh_order_blocks = [
        order_block for order_block in order_blocks if order_block.status == OrderBlockStatus.FRESH
    ]
    mitigated_order_blocks = [
        order_block
        for order_block in order_blocks
        if order_block.status == OrderBlockStatus.MITIGATED
    ]
    invalidated_order_blocks = [
        order_block
        for order_block in order_blocks
        if order_block.status == OrderBlockStatus.INVALIDATED
    ]
    return fresh_order_blocks, mitigated_order_blocks, invalidated_order_blocks


def _filter_structure_breaks_by_displacement(
    df: pd.DataFrame,
    breaks: list[StructureBreak],
    pattern_config: SmartMoneyPatternConfig,
) -> list[StructureBreak]:
    """설정된 경우 ATR 대비 body가 작은 구조 돌파를 제외한다."""
    multiplier = pattern_config.displacement_atr_multiplier
    if multiplier <= 0 or not breaks:
        return list(breaks)
    if not all(column in df.columns for column in _REQUIRED_OHLC_COLUMNS):
        return list(breaks)

    filtered: list[StructureBreak] = []
    for structure_break in breaks:
        atr = _average_true_range_at(df, structure_break.bar_index, pattern_config.atr_period)
        if atr is None or atr <= 0:
            filtered.append(structure_break)
            continue
        body = abs(
            float(df["close"].iloc[structure_break.bar_index])
            - float(df["open"].iloc[structure_break.bar_index])
        )
        if body >= atr * multiplier:
            filtered.append(structure_break)
    return filtered


def _average_true_range_at(df: pd.DataFrame, bar_index: int, period: int) -> float | None:
    """bar_index 시점까지의 단순 ATR을 계산한다."""
    if bar_index < 0 or bar_index >= len(df):
        return None
    start_index = max(0, bar_index - period + 1)
    ranges: list[float] = []
    for index in range(start_index, bar_index + 1):
        high = float(df["high"].iloc[index])
        low = float(df["low"].iloc[index])
        if index == 0:
            ranges.append(high - low)
            continue
        previous_close = float(df["close"].iloc[index - 1])
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    if not ranges:
        return None
    return sum(ranges) / len(ranges)


def _select_recent_patterns(
    df: pd.DataFrame,
    patterns: list[CandlePattern],
) -> list[CandlePattern]:
    """최근 N개 캔들 구간의 패턴만 유지한다."""
    if len(df) == 0:
        return []

    start_index = max(0, len(df) - RECENT_PATTERN_LOOKBACK)
    return [pattern for pattern in patterns if pattern.bar_index >= start_index]


def _build_summary(report: TimeframePatternReport) -> PatternSummary:
    """리포트의 상태별 개수 요약을 생성한다."""
    bullish_pattern_count = sum(
        1
        for pattern in report.recent_candle_patterns
        if pattern.direction == CandleDirection.BULLISH
    )
    bearish_pattern_count = sum(
        1
        for pattern in report.recent_candle_patterns
        if pattern.direction == CandleDirection.BEARISH
    )
    neutral_pattern_count = sum(
        1
        for pattern in report.recent_candle_patterns
        if pattern.direction == CandleDirection.NEUTRAL
    )

    return PatternSummary(
        swing_count=len(report.swings),
        structure_break_count=len(report.structure_breaks),
        open_fvg_count=len(report.open_fvgs),
        touched_fvg_count=len(report.touched_fvgs),
        filled_fvg_count=len(report.filled_fvgs),
        fresh_order_block_count=len(report.fresh_order_blocks),
        mitigated_order_block_count=len(report.mitigated_order_blocks),
        invalidated_order_block_count=len(report.invalidated_order_blocks),
        liquidity_sweep_count=len(report.liquidity_sweeps),
        bullish_pattern_count=bullish_pattern_count,
        bearish_pattern_count=bearish_pattern_count,
        neutral_pattern_count=neutral_pattern_count,
    )
