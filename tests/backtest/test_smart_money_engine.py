"""PR-12: Smart Money 백테스트 엔진 테스트."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pytest

from src.analysis.smart_money.models import SmartMoneySignal


def _frame(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame을 만든다."""
    index = pd.date_range("2024-01-02 09:30", periods=len(closes), freq="5min")
    open_values = opens if opens is not None else closes
    low_values = (
        lows if lows is not None else [min(o, c) - 1.0 for o, c in zip(open_values, closes)]
    )
    return pd.DataFrame(
        {
            "open": open_values,
            "high": [max(o, c) + 1.0 for o, c in zip(open_values, closes)],
            "low": low_values,
            "close": closes,
            "volume": [10_000.0] * len(closes),
        },
        index=index,
    )


def _dataset(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """동일한 fixture를 세 timeframe에 공급한다."""
    return {"5m": frame, "1h": frame, "1d": frame}


def _signal(value: str, *, invalidation: float | None = None) -> SmartMoneySignal:
    """테스트용 SmartMoneySignal을 만든다."""
    return SmartMoneySignal(
        signal=value,
        confidence=0.8 if value != "HOLD" else 0.0,
        score=0.8 if value == "BUY" else -0.8 if value == "SELL" else 0.0,
        risk_level="LOW",
        entry_zone=(100.0, 101.0) if value == "BUY" else None,
        invalidation_level=invalidation,
        reasons=[f"test {value}"],
    )


def test_walk_forward_uses_only_past_rows_and_enters_next_candle() -> None:
    """시그널 시점까지의 캔들만 보고 다음 캔들 open으로 진입한다."""
    from src.backtest.smart_money_engine import SmartMoneyBacktestConfig, run_smart_money_backtest

    frame = _frame([100.0, 101.0, 102.0, 103.0, 104.0])
    signal_timestamps: list[pd.Timestamp] = []
    seen_window_ends: list[pd.Timestamp] = []

    def resolver(windows: Mapping[str, pd.DataFrame], _config: object) -> SmartMoneySignal:
        window = windows["5m"]
        signal_timestamps.append(window.index[-1])
        seen_window_ends.append(window.index.max())
        if window.index[-1] == frame.index[1]:
            return _signal("BUY", invalidation=98.0)
        if window.index[-1] == frame.index[3]:
            return _signal("SELL")
        return _signal("HOLD")

    result = run_smart_money_backtest(
        _dataset(frame),
        config=SmartMoneyBacktestConfig(
            initial_capital=1_000.0,
            position_size_pct=1.0,
            min_history_bars=1,
            commission_rate=0.0,
            slippage_rate=0.0,
        ),
        signal_resolver=resolver,
    )

    assert all(end == ts for end, ts in zip(seen_window_ends, signal_timestamps))
    assert result.trades[0].entry_time == frame.index[2].to_pydatetime()
    assert result.trades[0].entry_price == pytest.approx(frame["open"].iloc[2])
    assert result.trades[0].exit_time == frame.index[4].to_pydatetime()
    assert result.trades[0].exit_reason == "SELL_SIGNAL"


def test_invalidation_exits_before_holding_period() -> None:
    """BUY 이후 invalidation 하향 이탈이 발생하면 즉시 청산한다."""
    from src.backtest.smart_money_engine import SmartMoneyBacktestConfig, run_smart_money_backtest

    frame = _frame(
        [100.0, 101.0, 102.0, 99.0, 105.0],
        lows=[99.0, 100.0, 101.0, 97.5, 104.0],
    )

    def resolver(windows: Mapping[str, pd.DataFrame], _config: object) -> SmartMoneySignal:
        if windows["5m"].index[-1] == frame.index[1]:
            return _signal("BUY", invalidation=98.0)
        return _signal("HOLD")

    result = run_smart_money_backtest(
        _dataset(frame),
        config=SmartMoneyBacktestConfig(
            initial_capital=1_000.0,
            position_size_pct=1.0,
            min_history_bars=1,
            max_holding_bars=10,
            commission_rate=0.0,
            slippage_rate=0.0,
        ),
        signal_resolver=resolver,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "INVALIDATION"
    assert result.trades[0].exit_time == frame.index[3].to_pydatetime()
    assert result.trades[0].exit_price == pytest.approx(98.0)


def test_last_bar_buy_signal_is_not_executed_without_next_candle() -> None:
    """마지막 캔들에서 나온 BUY는 다음 캔들이 없으므로 체결하지 않는다."""
    from src.backtest.smart_money_engine import SmartMoneyBacktestConfig, run_smart_money_backtest

    frame = _frame([100.0, 101.0])

    def resolver(windows: Mapping[str, pd.DataFrame], _config: object) -> SmartMoneySignal:
        if windows["5m"].index[-1] == frame.index[-1]:
            return _signal("BUY", invalidation=98.0)
        return _signal("HOLD")

    result = run_smart_money_backtest(
        _dataset(frame),
        config=SmartMoneyBacktestConfig(min_history_bars=1),
        signal_resolver=resolver,
    )

    assert result.metrics.total_trades == 0
    assert result.trades == []


def test_commission_and_slippage_are_reflected_in_trade_return() -> None:
    """수수료와 슬리피지가 진입/청산 가격과 순손익에 반영된다."""
    from src.backtest.smart_money_engine import SmartMoneyBacktestConfig, run_smart_money_backtest

    frame = _frame(
        [99.0, 100.0, 110.0],
        opens=[99.0, 100.0, 110.0],
        lows=[98.0, 99.0, 109.0],
    )

    def resolver(windows: Mapping[str, pd.DataFrame], _config: object) -> SmartMoneySignal:
        if windows["5m"].index[-1] == frame.index[0]:
            return _signal("BUY", invalidation=95.0)
        if windows["5m"].index[-1] == frame.index[1]:
            return _signal("SELL")
        return _signal("HOLD")

    result = run_smart_money_backtest(
        _dataset(frame),
        config=SmartMoneyBacktestConfig(
            initial_capital=1_000.0,
            position_size_pct=1.0,
            min_history_bars=1,
            commission_rate=0.01,
            slippage_rate=0.01,
        ),
        signal_resolver=resolver,
    )

    trade = result.trades[0]
    assert trade.quantity == 9
    assert trade.entry_price == pytest.approx(101.0)
    assert trade.exit_price == pytest.approx(108.9)
    assert trade.net_pnl == pytest.approx(52.209)
    assert result.final_equity == pytest.approx(1_052.209)
    assert result.metrics.win_rate == pytest.approx(1.0)
    assert result.metrics.profit_factor == float("inf")


def test_default_signal_resolver_runs_with_smart_money_public_api() -> None:
    """기본 resolver가 Smart Money public API를 사용해 signal history를 만든다."""
    from src.backtest.smart_money_engine import SmartMoneyBacktestConfig, run_smart_money_backtest

    frame = _frame([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])

    result = run_smart_money_backtest(
        _dataset(frame),
        config=SmartMoneyBacktestConfig(min_history_bars=3),
    )

    assert len(result.signal_history) == len(frame)
    assert set(result.metrics.signal_counts) == {"BUY", "SELL", "HOLD"}
    assert result.final_equity == pytest.approx(result.initial_capital)
