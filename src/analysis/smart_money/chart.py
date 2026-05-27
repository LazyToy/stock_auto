"""Smart Money 분석 결과를 Plotly 차트 주석으로 변환하는 도우미."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol, TypeVar

import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]

from src.analysis.ohlcv import normalize_ohlcv_frame
from src.analysis.smart_money.models import (
    FairValueGap,
    FVGDirection,
    FVGStatus,
    OrderBlock,
    OrderBlockDirection,
    OrderBlockStatus,
    SmartMoneySignal,
    SwingPoint,
    SwingType,
)
from src.analysis.smart_money.report import TimeframePatternReport

MAX_RECTANGLES_PER_TYPE: int = 5
_REQUIRED_CANDLE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")

_BULLISH_FVG_FILL = "rgba(31, 119, 180, 0.18)"
_BEARISH_FVG_FILL = "rgba(214, 39, 40, 0.16)"
_BULLISH_OB_FILL = "rgba(44, 160, 44, 0.18)"
_BEARISH_OB_FILL = "rgba(148, 103, 189, 0.18)"
_ENTRY_ZONE_FILL = "rgba(255, 193, 7, 0.16)"
_INVALIDATION_COLOR = "rgba(33, 37, 41, 0.90)"


class _RecentAnnotatedItem(Protocol):
    @property
    def bar_index(self) -> int: ...


_TRecentAnnotatedItem = TypeVar("_TRecentAnnotatedItem", bound=_RecentAnnotatedItem)


def build_smart_money_figure(
    df: pd.DataFrame,
    report: TimeframePatternReport,
    signal: SmartMoneySignal | None = None,
) -> go.Figure:
    """OHLC 차트에 Smart Money 패턴과 최종 신호 주석을 추가한 Figure를 만든다.

    Args:
        df: DatetimeIndex 또는 datetime 컬럼을 가진 OHLC DataFrame.
        report: timeframe 단위 Smart Money 패턴 리포트.
        signal: 선택 입력인 최종 Smart Money 신호.

    Returns:
        Plotly candlestick trace와 Smart Money annotation이 포함된 Figure.

    Raises:
        ValueError: 입력 타입이 public API 계약과 다르거나 OHLC 컬럼이 없는 경우.
    """
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df는 pandas DataFrame이어야 합니다.")
    if not isinstance(report, TimeframePatternReport):
        raise ValueError("report는 TimeframePatternReport여야 합니다.")
    if signal is not None and not isinstance(signal, SmartMoneySignal):
        raise ValueError("signal은 SmartMoneySignal이거나 None이어야 합니다.")

    chart_df = _prepare_chart_frame(df)
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_df.index,
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name="OHLC",
        )
    )

    _add_swing_markers(fig, report.swings)
    _add_fvg_rectangles(fig, chart_df, report)
    _add_order_block_rectangles(fig, chart_df, report)
    _add_signal_overlays(fig, chart_df, signal)
    _apply_layout(fig, report.timeframe)
    return fig


def _prepare_chart_frame(df: pd.DataFrame) -> pd.DataFrame:
    """거래량이 없는 OHLC 프레임도 허용하면서 차트 입력을 정규화한다."""
    chart_df = normalize_ohlcv_frame(df)
    missing = [column for column in _REQUIRED_CANDLE_COLUMNS if column not in chart_df.columns]
    if missing:
        raise ValueError("Smart Money 차트에 필요한 OHLC 컬럼이 없습니다: " + ", ".join(missing))
    return chart_df


def _add_swing_markers(fig: go.Figure, swings: Sequence[SwingPoint]) -> None:
    """스윙 고점과 스윙 저점 marker trace를 추가한다."""
    swing_highs = [swing for swing in swings if swing.swing_type == SwingType.HIGH]
    swing_lows = [swing for swing in swings if swing.swing_type == SwingType.LOW]

    if swing_highs:
        fig.add_trace(
            go.Scatter(
                x=[swing.timestamp for swing in swing_highs],
                y=[swing.price for swing in swing_highs],
                mode="markers",
                name="Swing High",
                marker={
                    "symbol": "triangle-down",
                    "size": 10,
                    "color": "#d62728",
                    "line": {"width": 1, "color": "#ffffff"},
                },
                hovertemplate="Swing High<br>%{x}<br>%{y:.2f}<extra></extra>",
            )
        )
    if swing_lows:
        fig.add_trace(
            go.Scatter(
                x=[swing.timestamp for swing in swing_lows],
                y=[swing.price for swing in swing_lows],
                mode="markers",
                name="Swing Low",
                marker={
                    "symbol": "triangle-up",
                    "size": 10,
                    "color": "#2ca02c",
                    "line": {"width": 1, "color": "#ffffff"},
                },
                hovertemplate="Swing Low<br>%{x}<br>%{y:.2f}<extra></extra>",
            )
        )


def _add_fvg_rectangles(
    fig: go.Figure,
    df: pd.DataFrame,
    report: TimeframePatternReport,
) -> None:
    fvgs = _select_recent(
        [*report.open_fvgs, *report.touched_fvgs, *report.filled_fvgs],
        MAX_RECTANGLES_PER_TYPE,
    )
    for fvg in fvgs:
        fillcolor = (
            _BULLISH_FVG_FILL if fvg.direction == FVGDirection.BULLISH else _BEARISH_FVG_FILL
        )
        line_color = "#1f77b4" if fvg.direction == FVGDirection.BULLISH else "#d62728"
        fig.add_shape(
            type="rect",
            name="smart_money_fvg",
            xref="x",
            yref="y",
            x0=fvg.created_at,
            x1=_annotation_end_timestamp(df, fvg.created_at),
            y0=fvg.lower,
            y1=fvg.upper,
            fillcolor=fillcolor,
            line={"color": line_color, "width": 1, "dash": _status_dash(fvg.status)},
            layer="below",
        )


def _add_order_block_rectangles(
    fig: go.Figure,
    df: pd.DataFrame,
    report: TimeframePatternReport,
) -> None:
    order_blocks = _select_recent(
        [
            *report.fresh_order_blocks,
            *report.mitigated_order_blocks,
            *report.invalidated_order_blocks,
        ],
        MAX_RECTANGLES_PER_TYPE,
    )
    for order_block in order_blocks:
        fillcolor = (
            _BULLISH_OB_FILL
            if order_block.direction == OrderBlockDirection.BULLISH
            else _BEARISH_OB_FILL
        )
        line_color = (
            "#2ca02c" if order_block.direction == OrderBlockDirection.BULLISH else "#9467bd"
        )
        fig.add_shape(
            type="rect",
            name="smart_money_order_block",
            xref="x",
            yref="y",
            x0=order_block.created_at,
            x1=_annotation_end_timestamp(df, order_block.created_at),
            y0=order_block.lower,
            y1=order_block.upper,
            fillcolor=fillcolor,
            line={
                "color": line_color,
                "width": 1,
                "dash": _status_dash(order_block.status),
            },
            layer="below",
        )


def _add_signal_overlays(
    fig: go.Figure,
    df: pd.DataFrame,
    signal: SmartMoneySignal | None,
) -> None:
    if signal is None:
        return

    _add_signal_annotation(fig, signal)
    if len(df.index) == 0:
        return

    x0, x1 = _full_width_x_range(df)
    if signal.entry_zone is not None:
        lower, upper = signal.entry_zone
        fig.add_shape(
            type="rect",
            name="smart_money_entry_zone",
            xref="x",
            yref="y",
            x0=x0,
            x1=x1,
            y0=lower,
            y1=upper,
            fillcolor=_ENTRY_ZONE_FILL,
            line={"color": "#ffbf00", "width": 1},
            layer="below",
        )

    if signal.invalidation_level is not None:
        fig.add_shape(
            type="line",
            name="smart_money_invalidation",
            xref="x",
            yref="y",
            x0=x0,
            x1=x1,
            y0=signal.invalidation_level,
            y1=signal.invalidation_level,
            line={"color": _INVALIDATION_COLOR, "width": 2, "dash": "dash"},
        )


def _add_signal_annotation(fig: go.Figure, signal: SmartMoneySignal) -> None:
    """최종 신호, 신뢰도, 리스크 수준을 차트 상단에 표시한다."""
    fig.add_annotation(
        name="smart_money_signal",
        text=_format_signal_annotation_text(signal),
        x=1.0,
        y=1.16,
        xref="paper",
        yref="paper",
        xanchor="right",
        yanchor="bottom",
        showarrow=False,
        align="right",
        bgcolor="rgba(255,255,255,0.92)",
        bordercolor="rgba(33,37,41,0.35)",
        borderwidth=1,
        borderpad=4,
        font={"size": 12, "color": "#212529"},
    )


def _format_signal_annotation_text(signal: SmartMoneySignal) -> str:
    """최종 신호 annotation에 사용할 고정 형식의 텍스트를 만든다."""
    confidence_pct = signal.confidence * 100
    return (
        f"신호: {signal.signal} | "
        f"신뢰도: {confidence_pct:.1f}% | "
        f"리스크: {signal.risk_level}"
    )


def _apply_layout(fig: go.Figure, timeframe: str) -> None:
    fig.update_layout(
        title=f"Smart Money {timeframe} Chart",
        template="plotly_white",
        hovermode="x unified",
        margin={"l": 48, "r": 24, "t": 76, "b": 48},
        legend={
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": 1.02,
            "yanchor": "bottom",
        },
        height=520,
        xaxis={"rangeslider": {"visible": False}, "title": None},
        yaxis={"title": "Price", "fixedrange": False},
    )


def _select_recent(
    items: Sequence[_TRecentAnnotatedItem],
    max_items: int,
) -> list[_TRecentAnnotatedItem]:
    sorted_items = sorted(items, key=lambda item: item.bar_index)
    return sorted_items[-max_items:]


def _annotation_end_timestamp(df: pd.DataFrame, start: datetime | pd.Timestamp) -> pd.Timestamp:
    if len(df.index) == 0:
        return pd.Timestamp(start)
    last_timestamp = pd.Timestamp(df.index[-1])
    start_timestamp = pd.Timestamp(start)
    return max(start_timestamp, last_timestamp)


def _full_width_x_range(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    first_timestamp = pd.Timestamp(df.index[0])
    last_timestamp = pd.Timestamp(df.index[-1])
    return first_timestamp, max(first_timestamp, last_timestamp)


def _status_dash(
    status: FVGStatus | OrderBlockStatus,
) -> Literal["solid", "dot", "dash"]:
    if status in (FVGStatus.FILLED, OrderBlockStatus.INVALIDATED):
        return "dot"
    if status in (FVGStatus.TOUCHED, OrderBlockStatus.MITIGATED):
        return "dash"
    return "solid"
