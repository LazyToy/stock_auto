"""PR-09: Smart Money Plotly chart annotation helper tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import pandas as pd

from src.analysis.smart_money.models import (
    FairValueGap,
    FVGDirection,
    FVGStatus,
    MarketStructure,
    OrderBlock,
    OrderBlockDirection,
    OrderBlockStatus,
    SmartMoneySignal,
    SwingPoint,
    SwingType,
)
from src.analysis.smart_money.report import PatternSummary, TimeframePatternReport


def _dt(offset: int) -> datetime:
    return datetime(2024, 1, 2) + timedelta(days=offset)


def _make_df(rows: int = 8) -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=rows, freq="1D")
    return pd.DataFrame(
        {
            "open": [100.0 + i for i in range(rows)],
            "high": [102.0 + i for i in range(rows)],
            "low": [99.0 + i for i in range(rows)],
            "close": [101.0 + i for i in range(rows)],
            "volume": [10_000 + i for i in range(rows)],
        },
        index=index,
    )


def _empty_report() -> TimeframePatternReport:
    return TimeframePatternReport(
        timeframe="1h",
        latest_close=107.0,
        latest_bar_index=7,
        market_structure=MarketStructure.RANGE,
        recent_swing_high=None,
        recent_swing_low=None,
        summary=PatternSummary(),
    )


def _fvg(
    direction: FVGDirection,
    status: FVGStatus,
    lower: float,
    upper: float,
    offset: int,
    bar_index: int,
) -> FairValueGap:
    return FairValueGap(
        direction=direction,
        status=status,
        lower=lower,
        upper=upper,
        created_at=_dt(offset),
        bar_index=bar_index,
    )


def _order_block(
    direction: OrderBlockDirection,
    status: OrderBlockStatus,
    lower: float,
    upper: float,
    offset: int,
    bar_index: int,
) -> OrderBlock:
    return OrderBlock(
        direction=direction,
        status=status,
        lower=lower,
        upper=upper,
        created_at=_dt(offset),
        bar_index=bar_index,
        break_at=_dt(offset + 1),
        break_bar_index=bar_index + 1,
    )


def _shape_count(fig, name: str) -> int:
    return sum(1 for shape in fig.layout.shapes if shape.name == name)


def _annotation_count(fig, name: str) -> int:
    return sum(1 for annotation in fig.layout.annotations if annotation.name == name)


class TestBuildSmartMoneyFigure(unittest.TestCase):
    def setUp(self) -> None:
        from src.analysis.smart_money.chart import build_smart_money_figure

        self.fn = build_smart_money_figure

    def test_figure_contains_candlestick_trace(self) -> None:
        fig = self.fn(_make_df(), _empty_report())

        self.assertEqual(len(fig.data), 1)
        self.assertEqual(fig.data[0].type, "candlestick")
        self.assertEqual(fig.data[0].name, "OHLC")

    def test_swing_points_are_added_as_marker_traces(self) -> None:
        report = _empty_report()
        report.swings = [
            SwingPoint(_dt(2), 106.0, SwingType.HIGH, 2),
            SwingPoint(_dt(4), 101.0, SwingType.LOW, 4),
        ]

        fig = self.fn(_make_df(), report)

        self.assertEqual([trace.name for trace in fig.data], ["OHLC", "Swing High", "Swing Low"])

    def test_fvg_rectangle_shape_count_matches_report(self) -> None:
        report = _empty_report()
        report.open_fvgs = [
            _fvg(FVGDirection.BULLISH, FVGStatus.OPEN, 101.0, 102.0, 2, 2),
        ]
        report.touched_fvgs = [
            _fvg(FVGDirection.BEARISH, FVGStatus.TOUCHED, 104.0, 105.0, 3, 3),
        ]
        report.filled_fvgs = [
            _fvg(FVGDirection.BULLISH, FVGStatus.FILLED, 102.5, 103.5, 4, 4),
        ]

        fig = self.fn(_make_df(), report)

        self.assertEqual(_shape_count(fig, "smart_money_fvg"), 3)

    def test_order_block_rectangle_shape_count_matches_report(self) -> None:
        report = _empty_report()
        report.fresh_order_blocks = [
            _order_block(OrderBlockDirection.BULLISH, OrderBlockStatus.FRESH, 99.0, 101.0, 2, 2),
        ]
        report.mitigated_order_blocks = [
            _order_block(
                OrderBlockDirection.BEARISH,
                OrderBlockStatus.MITIGATED,
                106.0,
                108.0,
                3,
                3,
            ),
        ]
        report.invalidated_order_blocks = [
            _order_block(
                OrderBlockDirection.BULLISH,
                OrderBlockStatus.INVALIDATED,
                98.0,
                100.0,
                4,
                4,
            ),
        ]

        fig = self.fn(_make_df(), report)

        self.assertEqual(_shape_count(fig, "smart_money_order_block"), 3)

    def test_entry_zone_and_invalidation_line_are_added_from_signal(self) -> None:
        signal = SmartMoneySignal(
            signal="BUY",
            confidence=0.72,
            score=0.72,
            risk_level="LOW",
            entry_zone=(102.0, 104.0),
            invalidation_level=99.5,
        )

        fig = self.fn(_make_df(), _empty_report(), signal)

        self.assertEqual(_shape_count(fig, "smart_money_entry_zone"), 1)
        self.assertEqual(_shape_count(fig, "smart_money_invalidation"), 1)

    def test_signal_annotation_contains_signal_confidence_and_risk(self) -> None:
        signal = SmartMoneySignal(
            signal="SELL",
            confidence=0.64321,
            score=-0.64,
            risk_level="MEDIUM",
        )

        fig = self.fn(_make_df(), _empty_report(), signal)

        self.assertEqual(_annotation_count(fig, "smart_money_signal"), 1)
        annotation_text = fig.layout.annotations[0].text
        self.assertIn("SELL", annotation_text)
        self.assertIn("64.3%", annotation_text)
        self.assertIn("MEDIUM", annotation_text)

    def test_non_dataframe_input_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "DataFrame"):
            self.fn([], _empty_report())  # type: ignore[arg-type]

    def test_empty_df_with_signal_skips_time_based_signal_shapes(self) -> None:
        empty_df = pd.DataFrame(
            {
                "open": pd.Series(dtype=float),
                "high": pd.Series(dtype=float),
                "low": pd.Series(dtype=float),
                "close": pd.Series(dtype=float),
                "volume": pd.Series(dtype=float),
            },
            index=pd.DatetimeIndex([], name="datetime"),
        )
        signal = SmartMoneySignal(
            signal="BUY",
            confidence=0.72,
            score=0.72,
            risk_level="LOW",
            entry_zone=(102.0, 104.0),
            invalidation_level=99.5,
        )

        fig = self.fn(empty_df, _empty_report(), signal)

        self.assertEqual(_annotation_count(fig, "smart_money_signal"), 1)
        self.assertEqual(_shape_count(fig, "smart_money_entry_zone"), 0)
        self.assertEqual(_shape_count(fig, "smart_money_invalidation"), 0)

    def test_recent_rectangle_limit_is_applied_per_type(self) -> None:
        report = _empty_report()
        report.open_fvgs = [
            _fvg(FVGDirection.BULLISH, FVGStatus.OPEN, 100.0 + i, 101.0 + i, i, i) for i in range(6)
        ]
        report.fresh_order_blocks = [
            _order_block(
                OrderBlockDirection.BULLISH,
                OrderBlockStatus.FRESH,
                98.0 + i,
                99.0 + i,
                i,
                i,
            )
            for i in range(6)
        ]

        fig = self.fn(_make_df(), report)

        self.assertEqual(_shape_count(fig, "smart_money_fvg"), 5)
        self.assertEqual(_shape_count(fig, "smart_money_order_block"), 5)

    def test_empty_report_does_not_fail_chart_generation(self) -> None:
        fig = self.fn(_make_df(), _empty_report())

        self.assertEqual(fig.data[0].type, "candlestick")
        self.assertEqual(len(fig.layout.shapes), 0)
        self.assertEqual(fig.layout.xaxis.rangeslider.visible, False)

    def test_chart_public_api_import_succeeds(self) -> None:
        from src.analysis.smart_money import build_smart_money_figure  # noqa: F401


if __name__ == "__main__":
    unittest.main()
