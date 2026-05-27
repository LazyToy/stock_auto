"""PR-07: 타임프레임별 패턴 분석 리포트 테스트.

`analyze_timeframe_patterns`, `analyze_multi_timeframe_patterns`의 공개 계약을 검증한다.
"""

from __future__ import annotations

import unittest

import pandas as pd


def _make_df(rows: list[dict], start: str = "2024-01-02", freq: str = "1D") -> pd.DataFrame:
    """테스트용 OHLCV DataFrame을 생성한다."""
    index = pd.date_range(start=start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=index)


def _make_bullish_fixture() -> pd.DataFrame:
    """상승 구조 + bullish FVG/OB + bullish 캔들 패턴을 포함한 fixture."""
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 104, "high": 105, "low": 103, "close": 104},
        {"open": 110, "high": 111, "low": 109, "close": 110},
        {"open": 106, "high": 107, "low": 105, "close": 106},
        {"open": 102, "high": 103, "low": 101, "close": 102},
        {"open": 108, "high": 109, "low": 107, "close": 108},
        {"open": 116, "high": 117, "low": 115, "close": 116},
        {"open": 112, "high": 113, "low": 111, "close": 112},
        {"open": 106, "high": 107, "low": 105, "close": 106},
        {"open": 114, "high": 115, "low": 109, "close": 110},
        {"open": 111, "high": 122, "low": 111, "close": 121},
        {"open": 120, "high": 126, "low": 119, "close": 125},
        {"open": 124, "high": 125, "low": 123, "close": 124},
    ]
    return _make_df(rows)


def _make_bearish_fixture() -> pd.DataFrame:
    """하락 구조 + bearish FVG/OB + bearish 캔들 패턴을 포함한 fixture."""
    rows = [
        {"open": 130, "high": 131, "low": 129, "close": 130},
        {"open": 126, "high": 127, "low": 125, "close": 126},
        {"open": 120, "high": 121, "low": 119, "close": 120},
        {"open": 124, "high": 125, "low": 123, "close": 124},
        {"open": 128, "high": 129, "low": 127, "close": 128},
        {"open": 122, "high": 123, "low": 121, "close": 122},
        {"open": 114, "high": 115, "low": 113, "close": 114},
        {"open": 118, "high": 119, "low": 117, "close": 118},
        {"open": 124, "high": 125, "low": 123, "close": 124},
        {"open": 116, "high": 121, "low": 115, "close": 120},
        {"open": 119, "high": 119, "low": 108, "close": 109},
        {"open": 110, "high": 111, "low": 104, "close": 105},
        {"open": 106, "high": 107, "low": 105, "close": 106},
    ]
    return _make_df(rows)


class TestAnalyzeTimeframePatterns(unittest.TestCase):
    """단일 timeframe 리포트 생성 계약을 검증한다."""

    def setUp(self) -> None:
        from src.analysis.smart_money.report import analyze_timeframe_patterns

        self.fn = analyze_timeframe_patterns

    def test_none_df_raises_value_error(self) -> None:
        """df=None이면 명시적으로 ValueError를 발생시킨다."""
        with self.assertRaises(ValueError):
            self.fn(None, "1h")  # type: ignore[arg-type]

    def test_non_datetime_index_raises_value_error(self) -> None:
        """DatetimeIndex가 아니면 ValueError를 발생시킨다."""
        df = pd.DataFrame(
            {
                "open": [1.0, 2.0],
                "high": [2.0, 3.0],
                "low": [0.5, 1.5],
                "close": [1.5, 2.5],
            }
        )
        with self.assertRaises(ValueError):
            self.fn(df, "1h")

    def test_unsorted_datetime_index_is_normalized_before_report_generation(self) -> None:
        """오름차순이 아닌 DatetimeIndex도 정규화 후 리포트를 생성한다."""
        df = _make_bullish_fixture().iloc[::-1]

        report = self.fn(df, "1h")

        self.assertEqual(report.latest_close, 124.0)
        self.assertEqual(report.summary.swing_count, 4)

    def test_non_numeric_ohlcv_column_raises_value_error(self) -> None:
        """숫자형이 아닌 OHLCV 컬럼이 있으면 명시적으로 ValueError를 발생시킨다."""
        df = _make_df(
            [
                {"open": "100.0", "high": 101.0, "low": 99.0, "close": 100.5},
                {"open": "101.0", "high": 102.0, "low": 100.0, "close": 101.5},
            ]
        )

        with self.assertRaises(ValueError):
            self.fn(df, "1h")

    def test_invalid_candle_without_volume_raises_value_error(self) -> None:
        """volume이 없어도 비정상 OHLC 캔들은 명시적으로 차단한다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
                {"open": 101.0, "high": 100.0, "low": 99.5, "close": 101.5},
            ]
        )

        with self.assertRaises(ValueError):
            self.fn(df, "1h")

    def test_duplicate_timestamp_is_normalized_before_report_generation(self) -> None:
        """중복 timestamp는 마지막 값을 유지하도록 정규화한 뒤 리포트를 생성한다."""
        duplicate_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-03"])
        df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
                {"open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5},
                {"open": 102.0, "high": 103.0, "low": 101.0, "close": 102.5},
            ],
            index=duplicate_index,
        )

        report = self.fn(df, "1h")

        self.assertEqual(report.latest_close, 102.5)
        self.assertEqual(report.timeframe, "1h")

    def test_bullish_fixture_report_contains_expected_sections(self) -> None:
        """상승 fixture에서 구조/FVG/OB/캔들/summary가 함께 채워진다."""
        from src.analysis.smart_money.models import MarketStructure

        report = self.fn(_make_bullish_fixture(), "1h")

        self.assertEqual(report.timeframe, "1h")
        self.assertEqual(report.latest_close, 124.0)
        self.assertEqual(report.market_structure, MarketStructure.BULLISH)
        self.assertIsNotNone(report.recent_swing_high)
        self.assertIsNotNone(report.recent_swing_low)
        self.assertEqual(report.recent_swing_high.price, 117.0)  # type: ignore[union-attr]
        self.assertEqual(report.recent_swing_low.price, 105.0)  # type: ignore[union-attr]
        self.assertEqual(len(report.swings), 4)
        self.assertEqual(len(report.structure_breaks), 2)
        self.assertEqual(len(report.open_fvgs), 3)
        self.assertEqual(len(report.touched_fvgs), 1)
        self.assertEqual(len(report.filled_fvgs), 4)
        self.assertEqual(len(report.fresh_order_blocks), 1)
        self.assertEqual(len(report.mitigated_order_blocks), 0)
        self.assertEqual(len(report.invalidated_order_blocks), 0)
        self.assertEqual(
            [pattern.name for pattern in report.recent_candle_patterns].count("strong_bullish"),
            2,
        )
        self.assertEqual(report.warnings, [])

        self.assertEqual(report.summary.swing_count, 4)
        self.assertEqual(report.summary.structure_break_count, 2)
        self.assertEqual(report.summary.open_fvg_count, 3)
        self.assertEqual(report.summary.touched_fvg_count, 1)
        self.assertEqual(report.summary.filled_fvg_count, 4)
        self.assertEqual(report.summary.fresh_order_block_count, 1)
        self.assertEqual(report.summary.mitigated_order_block_count, 0)
        self.assertEqual(report.summary.invalidated_order_block_count, 0)
        self.assertEqual(report.summary.bullish_pattern_count, 2)
        self.assertEqual(report.summary.bearish_pattern_count, 0)
        self.assertEqual(report.summary.neutral_pattern_count, 2)

    def test_pattern_config_controls_fvg_min_gap_threshold(self) -> None:
        """SmartMoneyPatternConfig의 fvg_min_gap_pct가 FVG 탐지에 전달된다."""
        from src.analysis.smart_money.models import SmartMoneyPatternConfig

        report = self.fn(
            _make_bullish_fixture(),
            "1h",
            pattern_config=SmartMoneyPatternConfig(fvg_min_gap_pct=0.50),
        )

        self.assertEqual(report.open_fvgs, [])
        self.assertEqual(report.touched_fvgs, [])
        self.assertEqual(report.filled_fvgs, [])
        self.assertEqual(report.summary.open_fvg_count, 0)

    def test_pattern_config_displacement_filter_removes_weak_structure_breaks(self) -> None:
        """ATR displacement 조건을 켜면 약한 구조 돌파는 리포트에서 제외된다."""
        from src.analysis.smart_money.models import SmartMoneyPatternConfig

        report = self.fn(
            _make_bullish_fixture(),
            "1h",
            pattern_config=SmartMoneyPatternConfig(displacement_atr_multiplier=10.0),
        )

        self.assertEqual(report.structure_breaks, [])
        self.assertEqual(report.fresh_order_blocks, [])
        self.assertEqual(report.summary.structure_break_count, 0)

    def test_pattern_config_controls_liquidity_sweep_detection(self) -> None:
        """리포트는 liquidity sweep을 탐지하고 summary에 집계한다."""
        from src.analysis.smart_money.models import LiquiditySweepDirection, SmartMoneyPatternConfig

        df = _make_df(
            [
                {"open": 100, "high": 101, "low": 99, "close": 100},
                {"open": 105, "high": 110, "low": 104, "close": 108},
                {"open": 107, "high": 108, "low": 103, "close": 104},
                {"open": 104, "high": 111, "low": 102, "close": 109.5},
            ]
        )

        report = self.fn(
            df,
            "5m",
            pattern_config=SmartMoneyPatternConfig(
                swing_left=1,
                swing_right=1,
                liquidity_sweep_tolerance_pct=0.001,
            ),
        )
        strict_report = self.fn(
            df,
            "5m",
            pattern_config=SmartMoneyPatternConfig(
                swing_left=1,
                swing_right=1,
                liquidity_sweep_tolerance_pct=0.02,
            ),
        )

        self.assertEqual(len(report.liquidity_sweeps), 1)
        self.assertEqual(report.liquidity_sweeps[0].direction, LiquiditySweepDirection.BEARISH)
        self.assertEqual(report.summary.liquidity_sweep_count, 1)
        self.assertEqual(strict_report.liquidity_sweeps, [])
        self.assertEqual(strict_report.summary.liquidity_sweep_count, 0)

    def test_bearish_fixture_report_contains_expected_sections(self) -> None:
        """하락 fixture에서 구조/FVG/OB/캔들/summary가 함께 채워진다."""
        from src.analysis.smart_money.models import MarketStructure

        report = self.fn(_make_bearish_fixture(), "15m")

        self.assertEqual(report.timeframe, "15m")
        self.assertEqual(report.latest_close, 106.0)
        self.assertEqual(report.market_structure, MarketStructure.BEARISH)
        self.assertIsNotNone(report.recent_swing_high)
        self.assertIsNotNone(report.recent_swing_low)
        self.assertEqual(report.recent_swing_high.price, 125.0)  # type: ignore[union-attr]
        self.assertEqual(report.recent_swing_low.price, 113.0)  # type: ignore[union-attr]
        self.assertEqual(len(report.swings), 4)
        self.assertEqual(len(report.structure_breaks), 2)
        self.assertEqual(len(report.open_fvgs), 3)
        self.assertEqual(len(report.touched_fvgs), 1)
        self.assertEqual(len(report.filled_fvgs), 4)
        self.assertEqual(len(report.fresh_order_blocks), 1)
        self.assertEqual(len(report.mitigated_order_blocks), 0)
        self.assertEqual(len(report.invalidated_order_blocks), 0)
        self.assertEqual(
            [pattern.name for pattern in report.recent_candle_patterns].count("strong_bearish"),
            2,
        )
        self.assertEqual(report.warnings, [])

        self.assertEqual(report.summary.swing_count, 4)
        self.assertEqual(report.summary.structure_break_count, 2)
        self.assertEqual(report.summary.open_fvg_count, 3)
        self.assertEqual(report.summary.touched_fvg_count, 1)
        self.assertEqual(report.summary.filled_fvg_count, 4)
        self.assertEqual(report.summary.fresh_order_block_count, 1)
        self.assertEqual(report.summary.mitigated_order_block_count, 0)
        self.assertEqual(report.summary.invalidated_order_block_count, 0)
        self.assertEqual(report.summary.bullish_pattern_count, 0)
        self.assertEqual(report.summary.bearish_pattern_count, 2)
        self.assertEqual(report.summary.neutral_pattern_count, 2)

    def test_insufficient_rows_add_warning(self) -> None:
        """데이터가 부족하면 warning을 남기고 빈 리포트를 반환한다."""
        report = self.fn(
            _make_df(
                [
                    {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.4},
                    {"open": 100.5, "high": 101.2, "low": 99.8, "close": 100.8},
                ]
            ),
            "5m",
        )

        self.assertEqual(report.latest_close, 100.8)
        self.assertEqual(report.swings, [])
        self.assertEqual(report.structure_breaks, [])
        self.assertEqual(report.open_fvgs, [])
        self.assertEqual(report.fresh_order_blocks, [])
        self.assertGreaterEqual(len(report.warnings), 1)
        self.assertTrue(any("부족" in warning for warning in report.warnings))

    def test_empty_recent_pattern_list_still_returns_report(self) -> None:
        """캔들 패턴이 비어 있어도 리포트 생성은 실패하지 않는다."""
        df = _make_df(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.4},
                {"open": 100.5, "high": 101.2, "low": 99.8, "close": 100.8},
                {"open": 100.7, "high": 101.4, "low": 100.1, "close": 101.0},
            ]
        )

        report = self.fn(df, "1d")

        self.assertEqual(report.timeframe, "1d")
        self.assertEqual(report.latest_close, 101.0)
        self.assertEqual(report.recent_candle_patterns, [])
        self.assertEqual(report.summary.bullish_pattern_count, 0)
        self.assertEqual(report.summary.bearish_pattern_count, 0)
        self.assertEqual(report.summary.neutral_pattern_count, 0)


class TestAnalyzeMultiTimeframePatterns(unittest.TestCase):
    """여러 timeframe 리포트 묶음 생성 계약을 검증한다."""

    def setUp(self) -> None:
        from src.analysis.smart_money.report import analyze_multi_timeframe_patterns

        self.fn = analyze_multi_timeframe_patterns

    def test_empty_dataset_returns_empty_dict(self) -> None:
        """빈 dataset이면 빈 dict를 반환한다."""
        self.assertEqual(self.fn({}), {})

    def test_none_dataset_raises_value_error(self) -> None:
        """dataset=None이면 ValueError를 발생시킨다."""
        with self.assertRaises(ValueError):
            self.fn(None)  # type: ignore[arg-type]

    def test_multi_timeframe_reports_are_returned_by_timeframe(self) -> None:
        """입력한 timeframe 키 기준으로 각 리포트를 반환한다."""
        reports = self.fn(
            {
                "1d": _make_bullish_fixture(),
                "1h": _make_bearish_fixture(),
            }
        )

        self.assertEqual(list(reports.keys()), ["1d", "1h"])
        self.assertEqual(reports["1d"].timeframe, "1d")
        self.assertEqual(reports["1h"].timeframe, "1h")
        self.assertEqual(reports["1d"].latest_close, 124.0)
        self.assertEqual(reports["1h"].latest_close, 106.0)

    def test_multi_timeframe_pattern_config_is_forwarded_to_each_report(self) -> None:
        """multi timeframe 분석도 동일한 pattern_config를 각 timeframe에 전달한다."""
        from src.analysis.smart_money.models import SmartMoneyPatternConfig

        reports = self.fn(
            {
                "1d": _make_bullish_fixture(),
                "1h": _make_bearish_fixture(),
            },
            pattern_config=SmartMoneyPatternConfig(fvg_min_gap_pct=0.50),
        )

        assert reports["1d"].summary.open_fvg_count == 0
        assert reports["1h"].summary.open_fvg_count == 0


class TestSmartMoneyReportPackageImport(unittest.TestCase):
    """smart_money 패키지 public API export를 검증한다."""

    def test_report_public_api_import_succeeds(self) -> None:
        """src.analysis.smart_money에서 report 관련 public API를 import할 수 있다."""
        from src.analysis.smart_money import (  # noqa: F401
            PatternSummary,
            TimeframePatternReport,
            analyze_multi_timeframe_patterns,
            analyze_timeframe_patterns,
        )


if __name__ == "__main__":
    unittest.main()
