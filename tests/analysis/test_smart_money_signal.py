"""PR-08: Smart Money 신호 점수화 엔진 테스트.

`score_timeframe_report`, `combine_multi_timeframe_signals` 공개 계약을 검증한다.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

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
    StructureBreak,
    SwingPoint,
    SwingType,
)
from src.analysis.smart_money.report import PatternSummary, TimeframePatternReport


def _dt(day_offset: int) -> datetime:
    """기준 시각에서 day_offset만큼 이동한 datetime을 만든다."""
    return datetime(2024, 1, 2) + timedelta(days=day_offset)


def _swing(price: float, swing_type: SwingType, day_offset: int, bar_index: int) -> SwingPoint:
    """테스트용 SwingPoint를 만든다."""
    return SwingPoint(
        timestamp=_dt(day_offset),
        price=price,
        swing_type=swing_type,
        bar_index=bar_index,
    )


def _break(
    direction: BreakDirection,
    break_type: BreakType,
    price: float,
    day_offset: int,
    bar_index: int,
) -> StructureBreak:
    """테스트용 StructureBreak를 만든다."""
    return StructureBreak(
        timestamp=_dt(day_offset),
        break_type=break_type,
        direction=direction,
        broken_level=price,
        bar_index=bar_index,
    )


def _fvg(
    direction: FVGDirection,
    status: FVGStatus,
    lower: float,
    upper: float,
    day_offset: int,
    bar_index: int,
) -> FairValueGap:
    """테스트용 FVG를 만든다."""
    return FairValueGap(
        direction=direction,
        lower=lower,
        upper=upper,
        created_at=_dt(day_offset),
        bar_index=bar_index,
        status=status,
    )


def _order_block(
    direction: OrderBlockDirection,
    status: OrderBlockStatus,
    lower: float,
    upper: float,
    day_offset: int,
    bar_index: int,
    break_day_offset: int,
    break_bar_index: int,
    strength: float = 1.0,
) -> OrderBlock:
    """테스트용 OrderBlock을 만든다."""
    return OrderBlock(
        direction=direction,
        lower=lower,
        upper=upper,
        created_at=_dt(day_offset),
        bar_index=bar_index,
        break_at=_dt(break_day_offset),
        break_bar_index=break_bar_index,
        status=status,
        strength=strength,
    )


def _pattern(
    name: str,
    direction: CandleDirection,
    day_offset: int,
    bar_index: int,
) -> CandlePattern:
    """테스트용 CandlePattern을 만든다."""
    return CandlePattern(
        name=name,
        direction=direction,
        timestamp=_dt(day_offset),
        bar_index=bar_index,
        strength=1.0,
    )


def _liquidity_sweep(
    direction: LiquiditySweepDirection,
    level: float,
    day_offset: int,
    bar_index: int,
    swept_swing_bar_index: int,
) -> LiquiditySweep:
    """테스트용 LiquiditySweep을 만든다."""
    return LiquiditySweep(
        direction=direction,
        swept_level=level,
        timestamp=_dt(day_offset),
        bar_index=bar_index,
        swept_swing_bar_index=swept_swing_bar_index,
    )


def _report(
    timeframe: str,
    latest_close: float | None,
    market_structure: MarketStructure,
    *,
    latest_bar_index: int | None = None,
    recent_swing_high: SwingPoint | None = None,
    recent_swing_low: SwingPoint | None = None,
    structure_breaks: list[StructureBreak] | None = None,
    open_fvgs: list[FairValueGap] | None = None,
    touched_fvgs: list[FairValueGap] | None = None,
    fresh_order_blocks: list[OrderBlock] | None = None,
    mitigated_order_blocks: list[OrderBlock] | None = None,
    liquidity_sweeps: list[LiquiditySweep] | None = None,
    recent_candle_patterns: list[CandlePattern] | None = None,
    warnings: list[str] | None = None,
) -> TimeframePatternReport:
    """테스트용 TimeframePatternReport를 만든다."""
    return TimeframePatternReport(
        timeframe=timeframe,
        latest_close=latest_close,
        latest_bar_index=latest_bar_index,
        market_structure=market_structure,
        recent_swing_high=recent_swing_high,
        recent_swing_low=recent_swing_low,
        swings=[],
        structure_breaks=list(structure_breaks or []),
        open_fvgs=list(open_fvgs or []),
        touched_fvgs=list(touched_fvgs or []),
        filled_fvgs=[],
        fresh_order_blocks=list(fresh_order_blocks or []),
        mitigated_order_blocks=list(mitigated_order_blocks or []),
        invalidated_order_blocks=[],
        liquidity_sweeps=list(liquidity_sweeps or []),
        recent_candle_patterns=list(recent_candle_patterns or []),
        summary=PatternSummary(),
        warnings=list(warnings or []),
    )


class TestScoreTimeframeReport(unittest.TestCase):
    """timeframe 단위 점수 기여를 검증한다."""

    def setUp(self) -> None:
        from src.analysis.smart_money.signal import SignalConfig, score_timeframe_report

        self.config = SignalConfig()
        self.fn = score_timeframe_report

    def test_hourly_bullish_setup_returns_expected_contributions(self) -> None:
        """1시간봉 bullish OB/FVG setup은 정해진 순서로 양수 기여를 만든다."""
        report = _report(
            "1h",
            121.0,
            MarketStructure.RANGE,
            mitigated_order_blocks=[
                _order_block(
                    OrderBlockDirection.BULLISH,
                    OrderBlockStatus.MITIGATED,
                    118.0,
                    120.0,
                    3,
                    3,
                    4,
                    4,
                )
            ],
            touched_fvgs=[_fvg(FVGDirection.BULLISH, FVGStatus.TOUCHED, 119.0, 120.5, 4, 4)],
        )

        contributions = self.fn(report, self.config)

        self.assertEqual(
            [item.component for item in contributions], ["order_block", "fair_value_gap"]
        )
        self.assertEqual([item.direction for item in contributions], ["BULLISH", "BULLISH"])
        self.assertAlmostEqual(sum(item.score for item in contributions), 0.35, places=6)

    def test_hourly_order_block_strength_increases_order_block_contribution(self) -> None:
        """거래량이 강한 OB는 1시간봉 setup 점수에 strength를 반영한다."""
        weak_report = _report(
            "1h",
            121.0,
            MarketStructure.RANGE,
            mitigated_order_blocks=[
                _order_block(
                    OrderBlockDirection.BULLISH,
                    OrderBlockStatus.MITIGATED,
                    118.0,
                    120.0,
                    3,
                    3,
                    4,
                    4,
                    strength=1.0,
                )
            ],
        )
        strong_report = _report(
            "1h",
            121.0,
            MarketStructure.RANGE,
            mitigated_order_blocks=[
                _order_block(
                    OrderBlockDirection.BULLISH,
                    OrderBlockStatus.MITIGATED,
                    118.0,
                    120.0,
                    3,
                    3,
                    4,
                    4,
                    strength=1.25,
                )
            ],
        )

        weak_score = self.fn(weak_report, self.config)[0].score
        strong_score = self.fn(strong_report, self.config)[0].score

        self.assertAlmostEqual(weak_score, 0.20, places=6)
        self.assertAlmostEqual(strong_score, 0.25, places=6)
        self.assertGreater(strong_score, weak_score)

    def test_minute_liquidity_sweep_returns_trigger_contribution(self) -> None:
        """5분봉 liquidity sweep은 trigger 점수에 반영된다."""
        report = _report(
            "5m",
            101.0,
            MarketStructure.RANGE,
            liquidity_sweeps=[
                _liquidity_sweep(
                    LiquiditySweepDirection.BULLISH,
                    100.0,
                    6,
                    6,
                    4,
                )
            ],
        )

        contributions = self.fn(report, self.config)

        self.assertEqual([item.component for item in contributions], ["liquidity_sweep"])
        self.assertEqual(contributions[0].direction, "BULLISH")
        self.assertAlmostEqual(contributions[0].score, 0.05, places=6)


class TestCombineMultiTimeframeSignals(unittest.TestCase):
    """멀티타임프레임 최종 신호 조합을 검증한다."""

    def setUp(self) -> None:
        from src.analysis.smart_money.signal import (
            SignalConfig,
            combine_multi_timeframe_signals,
        )

        self.config = SignalConfig()
        self.fn = combine_multi_timeframe_signals

    def test_all_bullish_alignment_returns_buy(self) -> None:
        """일봉/1시간봉/5분봉이 모두 bullish면 BUY를 반환한다."""
        reports = {
            "1d": _report(
                "1d",
                126.0,
                MarketStructure.BULLISH,
                recent_swing_high=_swing(132.0, SwingType.HIGH, 6, 6),
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.BOS, 124.0, 5, 5),
                ],
            ),
            "1h": _report(
                "1h",
                125.0,
                MarketStructure.RANGE,
                recent_swing_high=_swing(129.0, SwingType.HIGH, 5, 5),
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
                touched_fvgs=[_fvg(FVGDirection.BULLISH, FVGStatus.TOUCHED, 122.0, 123.5, 4, 4)],
            ),
            "5m": _report(
                "5m",
                124.5,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 123.0, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("hammer", CandleDirection.BULLISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "BUY")
        self.assertGreaterEqual(result.score, self.config.buy_threshold)
        self.assertGreaterEqual(result.confidence, self.config.min_confidence)
        self.assertEqual(result.entry_zone, (121.0, 123.0))
        self.assertEqual(result.invalidation_level, 121.0)
        self.assertIn(129.0, result.take_profit_candidates)
        self.assertEqual(result.risk_level, "LOW")
        self.assertEqual(len(result.contributions), 6)
        self.assertEqual(result.warnings, [])

    def test_all_bearish_alignment_returns_sell(self) -> None:
        """일봉/1시간봉/5분봉이 모두 bearish면 SELL을 반환한다."""
        reports = {
            "daily": _report(
                "daily",
                94.0,
                MarketStructure.BEARISH,
                recent_swing_low=_swing(90.0, SwingType.LOW, 6, 6),
                structure_breaks=[
                    _break(BreakDirection.BEARISH, BreakType.BOS, 96.0, 5, 5),
                ],
            ),
            "hourly": _report(
                "hourly",
                95.0,
                MarketStructure.RANGE,
                recent_swing_low=_swing(92.0, SwingType.LOW, 5, 5),
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BEARISH,
                        OrderBlockStatus.MITIGATED,
                        96.0,
                        98.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
                touched_fvgs=[_fvg(FVGDirection.BEARISH, FVGStatus.TOUCHED, 95.5, 97.0, 4, 4)],
            ),
            "minute_5": _report(
                "minute_5",
                94.5,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BEARISH, BreakType.CHOCH, 95.5, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("shooting_star", CandleDirection.BEARISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "SELL")
        self.assertLessEqual(result.score, self.config.sell_threshold)
        self.assertGreaterEqual(result.confidence, self.config.min_confidence)
        self.assertEqual(result.entry_zone, (96.0, 98.0))
        self.assertEqual(result.invalidation_level, 98.0)
        self.assertIn(92.0, result.take_profit_candidates)
        self.assertEqual(result.risk_level, "LOW")

    def test_two_bullish_timeframes_and_one_neutral_returns_buy(self) -> None:
        """2개 timeframe만 bullish여도 threshold와 confirmation을 만족하면 BUY다."""
        reports = {
            "1d": _report("1d", 125.0, MarketStructure.BULLISH),
            "1h": _report(
                "1h",
                124.0,
                MarketStructure.RANGE,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
                touched_fvgs=[
                    _fvg(
                        FVGDirection.BULLISH,
                        FVGStatus.TOUCHED,
                        123.2,
                        123.7,
                        4,
                        4,
                    )
                ],
            ),
            "5m": _report("5m", 123.8, MarketStructure.RANGE),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "BUY")
        self.assertAlmostEqual(result.score, 0.65, places=6)
        self.assertAlmostEqual(result.confidence, 0.65, places=6)

    def test_daily_and_hourly_direction_conflict_returns_hold(self) -> None:
        """일봉과 1시간봉 방향이 충돌하면 5분봉 trigger가 있어도 HOLD다."""
        reports = {
            "1d": _report("1d", 126.0, MarketStructure.BULLISH),
            "1h": _report(
                "1h",
                119.0,
                MarketStructure.RANGE,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BEARISH,
                        OrderBlockStatus.MITIGATED,
                        120.0,
                        122.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
            ),
            "5m": _report(
                "5m",
                120.5,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 120.0, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("hammer", CandleDirection.BULLISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "HOLD")
        self.assertTrue(any("충돌" in reason for reason in result.reasons))
        self.assertGreater(len(result.warnings), 0)

    def test_only_minute_bullish_trigger_returns_hold(self) -> None:
        """5분봉 단독 trigger는 최종 BUY를 만들 수 없다."""
        reports = {
            "1d": _report("1d", 101.0, MarketStructure.RANGE),
            "1h": _report("1h", 101.2, MarketStructure.RANGE),
            "5m": _report(
                "5m",
                102.0,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 101.0, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("bullish_engulfing", CandleDirection.BULLISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "HOLD")
        self.assertAlmostEqual(result.score, 0.25, places=6)

    def test_insufficient_data_adds_warning_and_lowers_confidence(self) -> None:
        """데이터 부족 warning이 있으면 confidence가 감점되고 warning이 유지된다."""
        reports = {
            "1d": _report("1d", 126.0, MarketStructure.BULLISH),
            "1h": _report(
                "1h",
                125.0,
                MarketStructure.RANGE,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
                warnings=["insufficient_data"],
            ),
            "5m": _report(
                "5m",
                124.5,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 123.0, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("hammer", CandleDirection.BULLISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "BUY")
        self.assertLess(result.confidence, result.score)
        self.assertTrue(any("insufficient_data" in warning for warning in result.warnings))

    def test_stale_patterns_reduce_confidence_when_latest_bar_index_is_known(self) -> None:
        """latest_bar_index가 있으면 오래된 패턴은 confidence를 감점한다."""
        stale_reports = {
            "1d": _report("1d", 126.0, MarketStructure.BULLISH, latest_bar_index=20),
            "1h": _report(
                "1h",
                125.0,
                MarketStructure.RANGE,
                latest_bar_index=20,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
            ),
        }
        fresh_reports = {
            "1d": _report("1d", 126.0, MarketStructure.BULLISH, latest_bar_index=5),
            "1h": _report(
                "1h",
                125.0,
                MarketStructure.RANGE,
                latest_bar_index=5,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
            ),
        }

        stale_result = self.fn(stale_reports, self.config)
        fresh_result = self.fn(fresh_reports, self.config)

        self.assertLess(stale_result.confidence, fresh_result.confidence)

    def test_stale_penalty_uses_freshest_relevant_pattern(self) -> None:
        """fresh trigger가 있으면 오래된 보조 패턴 하나가 confidence를 과도하게 깎지 않는다."""
        from src.analysis.smart_money.signal import SignalConfig

        config = SignalConfig(
            timeframe_weights={"daily": 0.0, "hourly": 0.0, "minute_5": 1.0},
            buy_threshold=0.5,
            min_confirming_timeframes=1,
            stale_pattern_penalty_per_bar=0.01,
        )
        reports = {
            "1d": _report("1d", 102.0, MarketStructure.RANGE),
            "1h": _report("1h", 102.0, MarketStructure.RANGE),
            "5m": _report(
                "5m",
                102.0,
                MarketStructure.RANGE,
                latest_bar_index=20,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 101.0, 2, 2),
                ],
                recent_candle_patterns=[
                    _pattern("bullish_engulfing", CandleDirection.BULLISH, 20, 20),
                ],
            ),
        }

        result = self.fn(reports, config)

        self.assertAlmostEqual(result.confidence, 1.0, places=6)

    def test_hold_after_invalidation_penalty_clears_entry_fields(self) -> None:
        """invalidation penalty 후 HOLD로 바뀌면 entry/invalidation 필드는 비워진다."""
        from src.analysis.smart_money.signal import SignalConfig

        config = SignalConfig(min_confidence=0.65)
        reports = {
            "1d": _report("1d", 125.0, MarketStructure.BULLISH),
            "1h": _report(
                "1h",
                121.4,
                MarketStructure.RANGE,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
            ),
            "5m": _report("5m", 121.4, MarketStructure.RANGE),
        }

        result = self.fn(reports, config)

        self.assertEqual(result.signal, "HOLD")
        self.assertIsNone(result.entry_zone)
        self.assertIsNone(result.invalidation_level)

    def test_threshold_passed_but_confirmation_is_insufficient_returns_hold(self) -> None:
        """score는 넘겨도 confirming timeframe 수가 부족하면 HOLD다."""
        from src.analysis.smart_money.signal import SignalConfig

        config = SignalConfig(
            timeframe_weights={"daily": 0.0, "hourly": 0.0, "minute_5": 1.0},
            buy_threshold=0.5,
            sell_threshold=-0.5,
            min_confirming_timeframes=2,
        )
        reports = {
            "5m": _report(
                "5m",
                102.0,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 101.0, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("bullish_engulfing", CandleDirection.BULLISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, config)

        self.assertEqual(result.signal, "HOLD")
        self.assertGreaterEqual(result.score, config.buy_threshold)
        self.assertTrue(any("확인" in reason for reason in result.reasons))

    def test_threshold_passed_but_confidence_below_minimum_returns_hold(self) -> None:
        """score는 넘겨도 confidence가 min_confidence 미만이면 HOLD다."""
        from src.analysis.smart_money.signal import SignalConfig

        config = SignalConfig(min_confidence=0.95)
        reports = {
            "1d": _report("1d", 125.0, MarketStructure.BULLISH),
            "1h": _report(
                "1h",
                124.0,
                MarketStructure.RANGE,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
            ),
        }

        result = self.fn(reports, config)

        self.assertEqual(result.signal, "HOLD")
        self.assertGreaterEqual(result.score, config.buy_threshold)
        self.assertLess(result.confidence, config.min_confidence)

    def test_only_minute_bearish_trigger_returns_hold(self) -> None:
        """5분봉 단독 bearish trigger도 최종 SELL을 만들 수 없다."""
        reports = {
            "1d": _report("1d", 101.0, MarketStructure.RANGE),
            "1h": _report("1h", 100.8, MarketStructure.RANGE),
            "5m": _report(
                "5m",
                99.8,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BEARISH, BreakType.CHOCH, 100.5, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("bearish_engulfing", CandleDirection.BEARISH, 6, 6),
                ],
            ),
        }

        result = self.fn(reports, self.config)

        self.assertEqual(result.signal, "HOLD")
        self.assertAlmostEqual(result.score, -0.25, places=6)
        self.assertAlmostEqual(result.confidence, 0.25, places=6)

    def test_same_input_returns_same_score_and_reason_order(self) -> None:
        """동일 입력이면 동일 score와 reason 순서를 반환한다."""
        reports = {
            "1d": _report("1d", 126.0, MarketStructure.BULLISH),
            "1h": _report(
                "1h",
                125.0,
                MarketStructure.RANGE,
                mitigated_order_blocks=[
                    _order_block(
                        OrderBlockDirection.BULLISH,
                        OrderBlockStatus.MITIGATED,
                        121.0,
                        123.0,
                        3,
                        3,
                        4,
                        4,
                    )
                ],
                touched_fvgs=[_fvg(FVGDirection.BULLISH, FVGStatus.TOUCHED, 122.0, 123.5, 4, 4)],
            ),
            "5m": _report(
                "5m",
                124.5,
                MarketStructure.RANGE,
                structure_breaks=[
                    _break(BreakDirection.BULLISH, BreakType.CHOCH, 123.0, 5, 5),
                ],
                recent_candle_patterns=[
                    _pattern("hammer", CandleDirection.BULLISH, 6, 6),
                ],
            ),
        }

        result_one = self.fn(reports, self.config)
        result_two = self.fn(reports, self.config)

        self.assertEqual(result_one.signal, result_two.signal)
        self.assertEqual(result_one.score, result_two.score)
        self.assertEqual(result_one.confidence, result_two.confidence)
        self.assertEqual(result_one.reasons, result_two.reasons)


class TestSmartMoneySignalPackageImport(unittest.TestCase):
    """smart_money 패키지 public API export를 검증한다."""

    def test_signal_public_api_import_succeeds(self) -> None:
        """src.analysis.smart_money에서 signal 관련 public API를 import할 수 있다."""
        from src.analysis.smart_money import (  # noqa: F401
            SignalConfig,
            SignalContribution,
            SmartMoneySignal,
            LiquiditySweep,
            LiquiditySweepDirection,
            combine_multi_timeframe_signals,
            score_timeframe_report,
        )


if __name__ == "__main__":
    unittest.main()
