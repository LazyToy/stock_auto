"""멀티타임프레임 Smart Money 신호 점수화 엔진.

PR-08 범위:
    - timeframe별 관측 리포트를 점수 기여 항목으로 변환한다.
    - 일봉/1시간봉/5분봉을 조합해 BUY/SELL/HOLD와 confidence를 산출한다.
    - 자동주문, UI 연결, 외부 I/O는 포함하지 않는다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping

from src.analysis.candlestick_patterns import CandleDirection, CandlePattern
from src.analysis.smart_money.models import (
    BreakDirection,
    BreakType,
    FairValueGap,
    FVGDirection,
    FVGStatus,
    LiquiditySweep,
    LiquiditySweepDirection,
    MarketStructure,
    OrderBlock,
    OrderBlockDirection,
    OrderBlockStatus,
    SignalConfig,
    SignalContribution,
    SmartMoneySignal,
    StructureBreak,
)
from src.analysis.smart_money.report import TimeframePatternReport

_TIMEFRAME_ALIASES: dict[str, str] = {
    "1d": "daily",
    "d": "daily",
    "day": "daily",
    "daily": "daily",
    "1h": "hourly",
    "60m": "hourly",
    "60min": "hourly",
    "hourly": "hourly",
    "5m": "minute_5",
    "5min": "minute_5",
    "minute_5": "minute_5",
}
_TIMEFRAME_PRIORITY: dict[str, int] = {
    "daily": 0,
    "hourly": 1,
    "minute_5": 2,
}
_COMPONENT_PRIORITY: dict[str, int] = {
    "market_structure": 0,
    "structure_break": 1,
    "liquidity_sweep": 2,
    "order_block": 3,
    "fair_value_gap": 4,
    "candle_pattern": 5,
}
_DIRECTION_PRIORITY: dict[str, int] = {
    "BULLISH": 0,
    "BEARISH": 1,
    "NEUTRAL": 2,
}

_DAILY_STRUCTURE_RATIO: float = 0.75
_DAILY_BREAK_RATIO: float = 0.25
_HOURLY_OB_TOUCH_RATIO: float = 4.0 / 7.0
_HOURLY_OB_FRESH_RATIO: float = 3.0 / 7.0
_HOURLY_FVG_TOUCH_RATIO: float = 3.0 / 7.0
_HOURLY_FVG_OPEN_RATIO: float = 2.0 / 7.0
_MINUTE_BREAK_RATIO: float = 0.60
_MINUTE_LIQUIDITY_SWEEP_RATIO: float = 0.20
_MINUTE_PATTERN_RATIO: float = 0.40

_BULLISH_PATTERN_NAMES: set[str] = {"bullish_engulfing", "hammer", "strong_bullish"}
_BEARISH_PATTERN_NAMES: set[str] = {"bearish_engulfing", "shooting_star", "strong_bearish"}

_BUY_SIGNAL: str = "BUY"
_SELL_SIGNAL: str = "SELL"
_HOLD_SIGNAL: str = "HOLD"
_NEUTRAL_DIRECTION: str = "NEUTRAL"


def score_timeframe_report(
    report: TimeframePatternReport,
    config: SignalConfig,
) -> list[SignalContribution]:
    """단일 timeframe 리포트를 점수 기여 항목으로 변환한다."""
    if report is None:
        raise ValueError("report가 None입니다. TimeframePatternReport를 전달해주세요.")
    if config is None:
        raise ValueError("config가 None입니다. SignalConfig를 전달해주세요.")

    timeframe = _canonicalize_timeframe(report.timeframe)
    if timeframe == "daily":
        return _score_daily_report(report, config)
    if timeframe == "hourly":
        return _score_hourly_report(report, config)
    if timeframe == "minute_5":
        return _score_minute_report(report, config)
    return []


def combine_multi_timeframe_signals(
    reports: Mapping[str, TimeframePatternReport],
    config: SignalConfig,
) -> SmartMoneySignal:
    """멀티타임프레임 리포트를 조합해 최종 신호를 산출한다."""
    if reports is None:
        raise ValueError("reports가 None입니다. timeframe별 리포트 dict를 전달해주세요.")
    if config is None:
        raise ValueError("config가 None입니다. SignalConfig를 전달해주세요.")

    normalized_reports = _normalize_reports(reports)
    contributions = _collect_contributions(normalized_reports, config)
    score = round(sum(item.score for item in contributions), 6)

    direction_by_timeframe = _build_timeframe_directions(contributions)
    warnings = _collect_warnings(normalized_reports)
    penalties = _calculate_penalties(normalized_reports, config, warnings)
    max_abs_score = _resolve_max_abs_score(contributions, config)
    raw_confidence = min(1.0, abs(score) / max_abs_score)
    confidence = round(max(0.0, min(1.0, raw_confidence - penalties)), 6)

    bullish_confirmations = sum(
        1 for direction in direction_by_timeframe.values() if direction == "BULLISH"
    )
    bearish_confirmations = sum(
        1 for direction in direction_by_timeframe.values() if direction == "BEARISH"
    )

    reasons: list[str] = _build_base_reasons(contributions)
    gate_reasons, gate_warnings = _evaluate_gates(
        normalized_reports=normalized_reports,
        score=score,
        confidence=confidence,
        bullish_confirmations=bullish_confirmations,
        bearish_confirmations=bearish_confirmations,
        direction_by_timeframe=direction_by_timeframe,
        config=config,
    )
    reasons.extend(gate_reasons)
    warnings.extend(gate_warnings)
    warnings = _deduplicate_strings(warnings)
    reasons = _deduplicate_strings(reasons)

    signal = _decide_signal(
        score=score,
        confidence=confidence,
        bullish_confirmations=bullish_confirmations,
        bearish_confirmations=bearish_confirmations,
        direction_by_timeframe=direction_by_timeframe,
        normalized_reports=normalized_reports,
        config=config,
    )
    entry_zone, invalidation_level = _select_entry_and_invalidation(normalized_reports, signal)
    penalties += _calculate_invalidation_penalty(
        normalized_reports=normalized_reports,
        signal=signal,
        entry_zone=entry_zone,
        invalidation_level=invalidation_level,
        config=config,
    )
    confidence = round(max(0.0, min(1.0, raw_confidence - penalties)), 6)
    signal = _decide_signal(
        score=score,
        confidence=confidence,
        bullish_confirmations=bullish_confirmations,
        bearish_confirmations=bearish_confirmations,
        direction_by_timeframe=direction_by_timeframe,
        normalized_reports=normalized_reports,
        config=config,
    )
    if signal == _HOLD_SIGNAL:
        entry_zone = None
        invalidation_level = None
    if signal == _HOLD_SIGNAL and confidence < config.min_confidence:
        reasons.append("confidence가 최소 기준보다 낮아 HOLD를 유지합니다.")

    take_profit_candidates = _build_take_profit_candidates(
        normalized_reports=normalized_reports,
        signal=signal,
    )
    risk_level = _determine_risk_level(confidence, warnings)

    return SmartMoneySignal(
        signal=signal,
        confidence=confidence,
        score=score,
        risk_level=risk_level,
        entry_zone=entry_zone,
        invalidation_level=invalidation_level,
        take_profit_candidates=take_profit_candidates,
        reasons=_deduplicate_strings(reasons),
        warnings=warnings,
        contributions=contributions,
    )


def _score_daily_report(
    report: TimeframePatternReport,
    config: SignalConfig,
) -> list[SignalContribution]:
    """일봉 리포트를 점수화한다."""
    contributions: list[SignalContribution] = []
    weight = _weight_for(report, config)

    if report.market_structure == MarketStructure.BULLISH:
        contributions.append(
            _make_contribution(
                report.timeframe,
                "market_structure",
                "BULLISH",
                weight * _DAILY_STRUCTURE_RATIO,
                "일봉 구조가 상승 방향을 유지합니다.",
            )
        )
    elif report.market_structure == MarketStructure.BEARISH:
        contributions.append(
            _make_contribution(
                report.timeframe,
                "market_structure",
                "BEARISH",
                -(weight * _DAILY_STRUCTURE_RATIO),
                "일봉 구조가 하락 방향을 유지합니다.",
            )
        )

    latest_break = _latest_structure_break(report.structure_breaks)
    if latest_break is not None:
        break_score = weight * _DAILY_BREAK_RATIO
        if latest_break.direction == BreakDirection.BULLISH:
            contributions.append(
                _make_contribution(
                    report.timeframe,
                    "structure_break",
                    "BULLISH",
                    break_score,
                    f"일봉에서 bullish {latest_break.break_type.value}가 확인되었습니다.",
                )
            )
        else:
            contributions.append(
                _make_contribution(
                    report.timeframe,
                    "structure_break",
                    "BEARISH",
                    -break_score,
                    f"일봉에서 bearish {latest_break.break_type.value}가 확인되었습니다.",
                )
            )

    return contributions


def _score_hourly_report(
    report: TimeframePatternReport,
    config: SignalConfig,
) -> list[SignalContribution]:
    """1시간봉 리포트를 점수화한다."""
    contributions: list[SignalContribution] = []
    weight = _weight_for(report, config)

    best_order_block = _best_order_block(report)
    if best_order_block is not None:
        is_touched = best_order_block.status == OrderBlockStatus.MITIGATED
        ratio = _HOURLY_OB_TOUCH_RATIO if is_touched else _HOURLY_OB_FRESH_RATIO
        direction = (
            "BULLISH" if best_order_block.direction == OrderBlockDirection.BULLISH else "BEARISH"
        )
        sign = 1.0 if direction == "BULLISH" else -1.0
        strength = max(0.0, float(best_order_block.strength))
        state_text = "touched" if is_touched else "fresh"
        contributions.append(
            _make_contribution(
                report.timeframe,
                "order_block",
                direction,
                sign * weight * ratio * strength,
                f"1시간봉 {direction.lower()} 오더블록이 {state_text} 상태입니다.",
            )
        )

    best_fvg = _best_fvg(report)
    if best_fvg is not None:
        is_touched = best_fvg.status == FVGStatus.TOUCHED
        ratio = _HOURLY_FVG_TOUCH_RATIO if is_touched else _HOURLY_FVG_OPEN_RATIO
        direction = "BULLISH" if best_fvg.direction == FVGDirection.BULLISH else "BEARISH"
        sign = 1.0 if direction == "BULLISH" else -1.0
        state_text = "touched" if is_touched else "open"
        contributions.append(
            _make_contribution(
                report.timeframe,
                "fair_value_gap",
                direction,
                sign * weight * ratio,
                f"1시간봉 {direction.lower()} FVG가 {state_text} 상태입니다.",
            )
        )

    return contributions


def _score_minute_report(
    report: TimeframePatternReport,
    config: SignalConfig,
) -> list[SignalContribution]:
    """5분봉 리포트를 점수화한다."""
    contributions: list[SignalContribution] = []
    weight = _weight_for(report, config)

    latest_break = _latest_structure_break(report.structure_breaks)
    if latest_break is not None:
        direction = "BULLISH" if latest_break.direction == BreakDirection.BULLISH else "BEARISH"
        sign = 1.0 if direction == "BULLISH" else -1.0
        contributions.append(
            _make_contribution(
                report.timeframe,
                "structure_break",
                direction,
                sign * weight * _MINUTE_BREAK_RATIO,
                f"5분봉에서 {direction.lower()} {latest_break.break_type.value}가 확인되었습니다.",
            )
        )

    latest_sweep = _latest_liquidity_sweep(report.liquidity_sweeps)
    if latest_sweep is not None:
        direction = (
            "BULLISH" if latest_sweep.direction == LiquiditySweepDirection.BULLISH else "BEARISH"
        )
        sign = 1.0 if direction == "BULLISH" else -1.0
        contributions.append(
            _make_contribution(
                report.timeframe,
                "liquidity_sweep",
                direction,
                sign * weight * _MINUTE_LIQUIDITY_SWEEP_RATIO,
                f"5분봉에서 {direction.lower()} liquidity sweep이 확인되었습니다.",
            )
        )

    best_pattern = _best_pattern(report.recent_candle_patterns, config)
    if best_pattern is not None:
        direction = _pattern_direction(best_pattern)
        if direction != _NEUTRAL_DIRECTION:
            sign = 1.0 if direction == "BULLISH" else -1.0
            contributions.append(
                _make_contribution(
                    report.timeframe,
                    "candle_pattern",
                    direction,
                    sign * weight * _MINUTE_PATTERN_RATIO,
                    f"5분봉에서 {best_pattern.name} 패턴이 확인되었습니다.",
                )
            )

    return contributions


def _normalize_reports(
    reports: Mapping[str, TimeframePatternReport],
) -> dict[str, TimeframePatternReport]:
    """timeframe alias를 표준 키로 정규화한다."""
    normalized: dict[str, TimeframePatternReport] = {}
    for timeframe, report in reports.items():
        candidate = report.timeframe if report is not None else timeframe
        normalized[_canonicalize_timeframe(candidate)] = report
    return normalized


def _collect_contributions(
    reports: Mapping[str, TimeframePatternReport],
    config: SignalConfig,
) -> list[SignalContribution]:
    """전체 timeframe 기여 항목을 수집한다."""
    items: list[SignalContribution] = []
    for timeframe in ("daily", "hourly", "minute_5"):
        report = reports.get(timeframe)
        if report is None:
            continue
        items.extend(score_timeframe_report(report, config))
    return sorted(
        items,
        key=lambda item: (
            _TIMEFRAME_PRIORITY.get(_canonicalize_timeframe(item.timeframe), 99),
            _COMPONENT_PRIORITY.get(item.component, 99),
            _DIRECTION_PRIORITY.get(item.direction, 99),
            item.reason,
        ),
    )


def _build_timeframe_directions(
    contributions: list[SignalContribution],
) -> dict[str, str]:
    """timeframe별 순방향 점수 합으로 confirming 방향을 판단한다."""
    score_by_timeframe: dict[str, float] = defaultdict(float)
    for item in contributions:
        score_by_timeframe[_canonicalize_timeframe(item.timeframe)] += item.score

    directions: dict[str, str] = {}
    for timeframe, score in score_by_timeframe.items():
        if score > 0:
            directions[timeframe] = "BULLISH"
        elif score < 0:
            directions[timeframe] = "BEARISH"
        else:
            directions[timeframe] = _NEUTRAL_DIRECTION
    return directions


def _collect_warnings(reports: Mapping[str, TimeframePatternReport]) -> list[str]:
    """리포트 warning과 누락 timeframe warning을 수집한다."""
    warnings: list[str] = []
    for timeframe in ("daily", "hourly", "minute_5"):
        report = reports.get(timeframe)
        if report is None:
            warnings.append(f"{timeframe} timeframe 리포트가 없어 신호 신뢰도가 낮아집니다.")
            continue
        warnings.extend(report.warnings)
    return warnings


def _calculate_penalties(
    reports: Mapping[str, TimeframePatternReport],
    config: SignalConfig,
    warnings: list[str],
) -> float:
    """confidence에 적용할 penalty를 계산한다."""
    penalty = 0.0
    if _has_direction_conflict(
        reports, _build_timeframe_directions(_collect_contributions(reports, config))
    ):
        penalty += config.conflict_penalty

    for timeframe in ("daily", "hourly", "minute_5"):
        report = reports.get(timeframe)
        if report is None or _report_has_data_issue(report):
            penalty += config.insufficient_data_penalty
        elif report.warnings:
            penalty += config.insufficient_data_penalty / 2.0
        penalty += _calculate_stale_penalty(report, config)

    if warnings and penalty == 0.0:
        penalty += config.insufficient_data_penalty / 2.0
    return penalty


def _calculate_stale_penalty(report: TimeframePatternReport | None, config: SignalConfig) -> float:
    """오래된 패턴에 대한 소규모 penalty를 계산한다."""
    if report is None:
        return 0.0

    latest_index = _latest_known_bar_index(report)
    if latest_index is None:
        return 0.0

    tracked_indices: list[int] = []
    latest_break = _latest_structure_break(report.structure_breaks)
    if latest_break is not None:
        tracked_indices.append(latest_break.bar_index)
    best_fvg = _best_fvg(report)
    if best_fvg is not None:
        tracked_indices.append(best_fvg.bar_index)
    best_order_block = _best_order_block(report)
    if best_order_block is not None:
        tracked_indices.append(best_order_block.break_bar_index)
    latest_sweep = _latest_liquidity_sweep(report.liquidity_sweeps)
    if latest_sweep is not None:
        tracked_indices.append(latest_sweep.bar_index)
    best_pattern = _best_pattern(report.recent_candle_patterns, config)
    if best_pattern is not None:
        tracked_indices.append(best_pattern.bar_index)

    if not tracked_indices:
        return 0.0

    freshest_relevant_index = max(tracked_indices)
    age = max(0, latest_index - freshest_relevant_index)
    return age * config.stale_pattern_penalty_per_bar


def _evaluate_gates(
    normalized_reports: Mapping[str, TimeframePatternReport],
    score: float,
    confidence: float,
    bullish_confirmations: int,
    bearish_confirmations: int,
    direction_by_timeframe: Mapping[str, str],
    config: SignalConfig,
) -> tuple[list[str], list[str]]:
    """최종 BUY/SELL/HOLD gate 사유와 warning을 만든다."""
    reasons: list[str] = []
    warnings: list[str] = []

    core_issues = sum(
        1
        for timeframe in ("daily", "hourly")
        if normalized_reports.get(timeframe) is None
        or _report_has_data_issue(normalized_reports.get(timeframe))
    )
    if core_issues >= 2:
        reasons.append("핵심 timeframe 데이터가 2개 이상 부족해 HOLD를 유지합니다.")
        warnings.append("핵심 timeframe 데이터 부족")

    if _has_direction_conflict(normalized_reports, direction_by_timeframe):
        reasons.append("상위 timeframe 방향 충돌로 HOLD를 유지합니다.")
        warnings.append("상위 timeframe 방향 충돌")

    if score >= config.buy_threshold and bullish_confirmations < config.min_confirming_timeframes:
        reasons.append("bullish 확인 timeframe 수가 부족해 HOLD를 유지합니다.")
    if score <= config.sell_threshold and bearish_confirmations < config.min_confirming_timeframes:
        reasons.append("bearish 확인 timeframe 수가 부족해 HOLD를 유지합니다.")
    if score >= config.buy_threshold and confidence < config.min_confidence:
        reasons.append("confidence가 BUY 최소 기준보다 낮아 HOLD를 유지합니다.")
    if score <= config.sell_threshold and confidence < config.min_confidence:
        reasons.append("confidence가 SELL 최소 기준보다 낮아 HOLD를 유지합니다.")

    return reasons, warnings


def _decide_signal(
    score: float,
    confidence: float,
    bullish_confirmations: int,
    bearish_confirmations: int,
    direction_by_timeframe: Mapping[str, str],
    normalized_reports: Mapping[str, TimeframePatternReport],
    config: SignalConfig,
) -> str:
    """gate 규칙을 적용해 최종 신호를 결정한다."""
    if _has_direction_conflict(normalized_reports, direction_by_timeframe):
        return _HOLD_SIGNAL

    core_issues = sum(
        1
        for timeframe in ("daily", "hourly")
        if normalized_reports.get(timeframe) is None
        or _report_has_data_issue(normalized_reports.get(timeframe))
    )
    if core_issues >= 2:
        return _HOLD_SIGNAL

    if (
        score >= config.buy_threshold
        and confidence >= config.min_confidence
        and bullish_confirmations >= config.min_confirming_timeframes
    ):
        return _BUY_SIGNAL

    if (
        score <= config.sell_threshold
        and confidence >= config.min_confidence
        and bearish_confirmations >= config.min_confirming_timeframes
    ):
        return _SELL_SIGNAL

    return _HOLD_SIGNAL


def _select_entry_and_invalidation(
    reports: Mapping[str, TimeframePatternReport],
    signal: str,
) -> tuple[tuple[float, float] | None, float | None]:
    """우선순위에 따라 entry zone과 invalidation level을 고른다."""
    if signal == _HOLD_SIGNAL:
        return None, None

    hourly_report = reports.get("hourly")
    if hourly_report is None:
        return None, None

    if signal == _BUY_SIGNAL:
        best_order_block = _best_directional_order_block(hourly_report, OrderBlockDirection.BULLISH)
        if best_order_block is not None:
            return (best_order_block.lower, best_order_block.upper), best_order_block.lower
        best_fvg = _best_directional_fvg(hourly_report, FVGDirection.BULLISH)
        if best_fvg is not None:
            return (best_fvg.lower, best_fvg.upper), best_fvg.lower
        return None, None

    best_order_block = _best_directional_order_block(hourly_report, OrderBlockDirection.BEARISH)
    if best_order_block is not None:
        return (best_order_block.lower, best_order_block.upper), best_order_block.upper
    best_fvg = _best_directional_fvg(hourly_report, FVGDirection.BEARISH)
    if best_fvg is not None:
        return (best_fvg.lower, best_fvg.upper), best_fvg.upper
    return None, None


def _calculate_invalidation_penalty(
    normalized_reports: Mapping[str, TimeframePatternReport],
    signal: str,
    entry_zone: tuple[float, float] | None,
    invalidation_level: float | None,
    config: SignalConfig,
) -> float:
    """진입 대비 무효화 거리가 과도하게 짧으면 confidence를 감점한다."""
    if signal == _HOLD_SIGNAL or entry_zone is None or invalidation_level is None:
        return 0.0

    latest_close = _latest_close_for_penalty(normalized_reports)
    if latest_close is None:
        return 0.0

    zone_width = max(entry_zone[1] - entry_zone[0], 1e-9)
    distance_to_invalidation = abs(latest_close - invalidation_level)
    if distance_to_invalidation <= zone_width * 0.5:
        return config.invalidation_proximity_penalty
    return 0.0


def _build_take_profit_candidates(
    normalized_reports: Mapping[str, TimeframePatternReport],
    signal: str,
) -> list[float]:
    """방향에 맞는 최근 스윙 레벨을 take profit 후보로 만든다."""
    if signal == _HOLD_SIGNAL:
        return []

    latest_close = _latest_close_for_penalty(normalized_reports)
    candidates: list[float] = []
    for timeframe in ("daily", "hourly", "minute_5"):
        report = normalized_reports.get(timeframe)
        if report is None or latest_close is None:
            continue
        if signal == _BUY_SIGNAL and report.recent_swing_high is not None:
            if report.recent_swing_high.price > latest_close:
                candidates.append(float(report.recent_swing_high.price))
        if signal == _SELL_SIGNAL and report.recent_swing_low is not None:
            if report.recent_swing_low.price < latest_close:
                candidates.append(float(report.recent_swing_low.price))
    return sorted(set(candidates))


def _determine_risk_level(confidence: float, warnings: list[str]) -> str:
    """confidence와 warning 수를 바탕으로 risk level을 정한다."""
    if confidence >= 0.75 and not warnings:
        return "LOW"
    if confidence >= 0.55:
        return "MEDIUM"
    return "HIGH"


def _build_base_reasons(contributions: list[SignalContribution]) -> list[str]:
    """기여 항목에서 기본 reason 순서를 만든다."""
    return [item.reason for item in contributions]


def _canonicalize_timeframe(timeframe: str) -> str:
    """timeframe alias를 표준 키로 변환한다."""
    normalized = (timeframe or "").strip().lower()
    return _TIMEFRAME_ALIASES.get(normalized, normalized)


def _weight_for(report: TimeframePatternReport, config: SignalConfig) -> float:
    """리포트 timeframe에 해당하는 가중치를 반환한다."""
    return float(config.timeframe_weights.get(_canonicalize_timeframe(report.timeframe), 0.0))


def _make_contribution(
    timeframe: str,
    component: str,
    direction: str,
    score: float,
    reason: str,
) -> SignalContribution:
    """SignalContribution 인스턴스를 만든다."""
    return SignalContribution(
        timeframe=timeframe,
        component=component,
        direction=direction,
        score=round(score, 6),
        reason=reason,
    )


def _latest_structure_break(
    structure_breaks: list[StructureBreak],
) -> StructureBreak | None:
    """가장 최근 구조 전환 이벤트를 반환한다."""
    if not structure_breaks:
        return None
    return max(
        structure_breaks,
        key=lambda item: (
            item.bar_index,
            item.timestamp,
            item.break_type.value,
            item.direction.value,
        ),
    )


def _latest_liquidity_sweep(
    liquidity_sweeps: list[LiquiditySweep],
) -> LiquiditySweep | None:
    """가장 최근 liquidity sweep을 반환한다."""
    if not liquidity_sweeps:
        return None
    return max(
        liquidity_sweeps,
        key=lambda item: (
            item.bar_index,
            item.timestamp,
            item.direction.value,
        ),
    )


def _best_order_block(report: TimeframePatternReport) -> OrderBlock | None:
    """가장 점수 영향이 큰 active order block을 고른다."""
    candidates = report.mitigated_order_blocks + report.fresh_order_blocks
    return _select_best_order_block(candidates)


def _best_directional_order_block(
    report: TimeframePatternReport,
    direction: OrderBlockDirection,
) -> OrderBlock | None:
    """방향이 일치하는 최적 order block을 고른다."""
    candidates = [
        order_block
        for order_block in (report.mitigated_order_blocks + report.fresh_order_blocks)
        if order_block.direction == direction
    ]
    return _select_best_order_block(candidates)


def _select_best_order_block(candidates: list[OrderBlock]) -> OrderBlock | None:
    """order block 후보 중 우선순위가 가장 높은 항목을 선택한다."""
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            1 if item.status == OrderBlockStatus.MITIGATED else 0,
            item.break_bar_index,
            item.bar_index,
            -item.lower,
            -item.upper,
        ),
    )


def _best_fvg(report: TimeframePatternReport) -> FairValueGap | None:
    """가장 점수 영향이 큰 active FVG를 고른다."""
    candidates = report.touched_fvgs + report.open_fvgs
    return _select_best_fvg(candidates)


def _best_directional_fvg(
    report: TimeframePatternReport,
    direction: FVGDirection,
) -> FairValueGap | None:
    """방향이 일치하는 최적 FVG를 고른다."""
    candidates = [
        fvg for fvg in (report.touched_fvgs + report.open_fvgs) if fvg.direction == direction
    ]
    return _select_best_fvg(candidates)


def _select_best_fvg(candidates: list[FairValueGap]) -> FairValueGap | None:
    """FVG 후보 중 우선순위가 가장 높은 항목을 선택한다."""
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            1 if item.status == FVGStatus.TOUCHED else 0,
            item.bar_index,
            -item.lower,
            -item.upper,
        ),
    )


def _best_pattern(
    patterns: list[CandlePattern],
    config: SignalConfig,
) -> CandlePattern | None:
    """최근 패턴 중 점수 반영 대상 1개를 선택한다."""
    if not patterns:
        return None

    limited_patterns = sorted(
        patterns,
        key=lambda item: (item.bar_index, item.timestamp, item.name),
    )[-config.max_patterns_per_type :]
    directional_patterns = [
        pattern
        for pattern in limited_patterns
        if _pattern_direction(pattern) in {"BULLISH", "BEARISH"}
    ]
    if not directional_patterns:
        return None

    return max(
        directional_patterns,
        key=lambda item: (
            item.bar_index,
            1 if item.name in _BULLISH_PATTERN_NAMES | _BEARISH_PATTERN_NAMES else 0,
            item.name,
        ),
    )


def _pattern_direction(pattern: CandlePattern) -> str:
    """패턴 이름과 direction을 바탕으로 BULLISH/BEARISH/NEUTRAL을 반환한다."""
    if pattern.name in _BULLISH_PATTERN_NAMES or pattern.direction == CandleDirection.BULLISH:
        return "BULLISH"
    if pattern.name in _BEARISH_PATTERN_NAMES or pattern.direction == CandleDirection.BEARISH:
        return "BEARISH"
    return _NEUTRAL_DIRECTION


def _report_has_data_issue(report: TimeframePatternReport | None) -> bool:
    """리포트의 데이터 부족/실패 여부를 보수적으로 판단한다."""
    if report is None:
        return True
    if report.latest_close is None:
        return True
    lowered_warnings = " ".join(report.warnings).lower()
    return "insufficient" in lowered_warnings or "부족" in lowered_warnings


def _has_direction_conflict(
    normalized_reports: Mapping[str, TimeframePatternReport],
    direction_by_timeframe: Mapping[str, str],
) -> bool:
    """일봉과 1시간봉 방향이 명확히 반대인지 확인한다."""
    if normalized_reports.get("daily") is None or normalized_reports.get("hourly") is None:
        return False
    return (
        direction_by_timeframe.get("daily") in {"BULLISH", "BEARISH"}
        and direction_by_timeframe.get("hourly") in {"BULLISH", "BEARISH"}
        and direction_by_timeframe.get("daily") != direction_by_timeframe.get("hourly")
    )


def _latest_known_bar_index(report: TimeframePatternReport) -> int | None:
    """리포트 안에서 추론 가능한 최신 bar index를 계산한다."""
    if report.latest_bar_index is not None:
        return report.latest_bar_index

    indices: list[int] = []
    if report.recent_swing_high is not None:
        indices.append(report.recent_swing_high.bar_index)
    if report.recent_swing_low is not None:
        indices.append(report.recent_swing_low.bar_index)
    indices.extend(item.bar_index for item in report.structure_breaks)
    indices.extend(item.bar_index for item in report.open_fvgs)
    indices.extend(item.bar_index for item in report.touched_fvgs)
    indices.extend(item.bar_index for item in report.filled_fvgs)
    indices.extend(item.bar_index for item in report.fresh_order_blocks)
    indices.extend(item.break_bar_index for item in report.mitigated_order_blocks)
    indices.extend(item.break_bar_index for item in report.invalidated_order_blocks)
    indices.extend(item.bar_index for item in report.liquidity_sweeps)
    indices.extend(item.bar_index for item in report.recent_candle_patterns)
    if not indices:
        return None
    return max(indices)


def _latest_close_for_penalty(
    normalized_reports: Mapping[str, TimeframePatternReport],
) -> float | None:
    """가능한 한 짧은 timeframe의 최신가를 우선 사용한다."""
    for timeframe in ("minute_5", "hourly", "daily"):
        report = normalized_reports.get(timeframe)
        if report is not None and report.latest_close is not None:
            return float(report.latest_close)
    return None


def _deduplicate_strings(values: list[str]) -> list[str]:
    """입력 순서를 유지하며 중복 문자열을 제거한다."""
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


def _resolve_max_abs_score(
    contributions: list[SignalContribution],
    config: SignalConfig,
) -> float:
    """설정된 전체 timeframe weight budget 기준으로 max_abs_score를 계산한다."""
    return max(sum(config.timeframe_weights.values()), 1e-9)
