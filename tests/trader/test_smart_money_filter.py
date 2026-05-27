import importlib
import logging
import logging.handlers
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from src.analysis.smart_money.models import SmartMoneySignal
from src.data.models import Account, OrderSide, Position


class _DummyHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return


def _import_auto_trader_with_dummy_handlers(monkeypatch):
    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", _DummyHandler)
    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", _DummyHandler)
    sys.modules.pop("src.trader.auto_trader", None)
    return importlib.import_module("src.trader.auto_trader")


def _signal(value: str) -> SmartMoneySignal:
    return SmartMoneySignal(
        signal=value,
        confidence=0.75,
        score=0.6 if value == "BUY" else -0.6 if value == "SELL" else 0.0,
        risk_level="MEDIUM",
        reasons=[f"{value} 테스트 신호"],
    )


def _selector_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "score": 2.0,
                "current_price": 50_000.0,
                "exchange": "KR",
            },
            {
                "ticker": "000660",
                "score": 1.8,
                "current_price": 80_000.0,
                "exchange": "KR",
            },
        ]
    )


def _make_trader(
    monkeypatch,
    *,
    config_values,
    resolver=None,
    selector_frame=None,
    positions=None,
    mock_exit=True,
):
    module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    monkeypatch.setattr(module.Config, "DATA_DIR", Path.cwd())
    monkeypatch.setattr(module, "send_notification", MagicMock())
    monkeypatch.setattr(
        module.AutoTrader,
        "_load_smart_money_trading_config",
        lambda self: module.build_smart_money_trading_config(config_values),
    )

    api_client = MagicMock()
    api_client.get_account_balance.return_value = Account(
        account_number="12345678",
        cash=1_000_000.0,
        positions=[] if positions is None else positions,
    )

    trader = module.AutoTrader(
        api_client=api_client,
        universe=["005930", "000660"],
        max_stocks=2,
        dry_run=True,
        market="KR",
        smart_money_signal_resolver=resolver,
    )
    trader.export_dashboard_state = MagicMock()
    if mock_exit:
        trader._process_exit_strategies = MagicMock(return_value=[])
    trader._place_order = MagicMock()
    frame = _selector_frame() if selector_frame is None else selector_frame
    trader.selector.calculate_metrics = MagicMock(return_value=frame)
    return module, trader


def test_feature_flag_off_preserves_selector_candidates(monkeypatch) -> None:
    resolver = MagicMock(side_effect=AssertionError("feature flag off에서는 호출되면 안 됩니다."))
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": False, "mode": "filter"},
        resolver=resolver,
    )

    trader.run_daily_routine()

    resolver.assert_not_called()
    assert trader.last_target_tickers == ["005930", "000660"]


def test_filter_mode_excludes_smart_money_sell_candidate(monkeypatch) -> None:
    resolver = MagicMock(
        side_effect=lambda symbol, market, exchange: (
            _signal("SELL") if symbol == "005930" else _signal("HOLD")
        )
    )
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
    )

    trader.run_daily_routine()

    assert trader.last_target_tickers == ["000660"]
    trader._place_order.assert_called_once()
    assert trader._place_order.call_args.args[2] == OrderSide.BUY


def test_filter_mode_keeps_candidate_when_smart_money_data_fails(monkeypatch) -> None:
    resolver = MagicMock(side_effect=RuntimeError("fixture 수집 실패"))
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
    )

    trader.run_daily_routine()

    assert trader.last_target_tickers == ["005930", "000660"]
    assert trader._place_order.call_count == 2


def test_filter_mode_records_dry_run_decision_log(monkeypatch, caplog) -> None:
    resolver = MagicMock(return_value=_signal("SELL"))
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
    )

    with caplog.at_level(logging.INFO):
        trader.run_daily_routine()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Smart Money dry-run" in message for message in messages)
    assert any("005930" in message and "제외" in message for message in messages)


def test_execute_mode_records_signal_without_filtering(monkeypatch) -> None:
    resolver = MagicMock(return_value=_signal("SELL"))
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "execute"},
        resolver=resolver,
    )

    trader.run_daily_routine()

    assert resolver.call_count == 2
    assert trader.last_target_tickers == ["005930", "000660"]


def test_load_smart_money_trading_config_reads_yaml(monkeypatch, tmp_path) -> None:
    module = _import_auto_trader_with_dummy_handlers(monkeypatch)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "trading.yaml").write_text(
        "\n".join(
            [
                "smart_money:",
                "  enabled: true",
                "  mode: filter",
                "  buy_score_bonus: 0.3",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module.Config, "BASE_DIR", tmp_path)
    trader = object.__new__(module.AutoTrader)

    config = trader._load_smart_money_trading_config()

    assert config.enabled is True
    assert config.mode == "filter"
    assert config.buy_score_bonus == 0.3


def test_resolve_smart_money_signal_uses_analysis_yaml_config(monkeypatch) -> None:
    """실제 resolver는 smart_money.signal/patterns 설정을 분석 파이프라인에 전달한다."""
    module = _import_auto_trader_with_dummy_handlers(monkeypatch)

    import pandas as pd
    import src.analysis.smart_money as smart_money
    from src.analysis.timeframes import MultiTimeframeDataset, Timeframe, TimeframeData

    signal_config = smart_money.SignalConfig(buy_threshold=0.62)
    pattern_config = smart_money.SmartMoneyPatternConfig(fvg_min_gap_pct=0.50)
    calls = {}

    class FakeFetcher:
        def fetch_symbol(self, symbol: str, market: str, exchange: str) -> MultiTimeframeDataset:
            frame = pd.DataFrame(
                [{"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}],
                index=pd.date_range("2024-01-02", periods=1),
            )
            return MultiTimeframeDataset(
                symbol=symbol,
                market=market,
                exchange=exchange,
                timeframes={
                    Timeframe.DAY_1: TimeframeData(
                        timeframe=Timeframe.DAY_1,
                        data=frame,
                        source="test",
                    )
                },
            )

    def fake_load_config():
        return signal_config, pattern_config

    def fake_analyze(frames, pattern_config=None):
        calls["frames"] = frames
        calls["pattern_config"] = pattern_config
        return {"1d": object()}

    def fake_combine(reports, config):
        calls["signal_config"] = config
        return _signal("HOLD")

    monkeypatch.setattr(smart_money, "load_smart_money_analysis_config", fake_load_config)
    monkeypatch.setattr(smart_money, "analyze_multi_timeframe_patterns", fake_analyze)
    monkeypatch.setattr(smart_money, "combine_multi_timeframe_signals", fake_combine)

    trader = object.__new__(module.AutoTrader)
    trader._smart_money_fetcher = FakeFetcher()

    result = trader._resolve_smart_money_signal("AAPL", "US", "NASD")

    assert result.signal == "HOLD"
    assert calls["signal_config"] is signal_config
    assert calls["pattern_config"] is pattern_config
    assert list(calls["frames"].keys()) == ["1d"]


def test_advisory_mode_does_not_apply_buy_bonus(monkeypatch) -> None:
    resolver = MagicMock(return_value=_signal("BUY"))
    selector_frame = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "score": 0.9,
                "current_price": 50_000.0,
                "exchange": "KR",
            }
        ]
    )
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "advisory", "buy_score_bonus": 0.2},
        resolver=resolver,
        selector_frame=selector_frame,
    )

    trader.run_daily_routine()

    assert trader.last_top_stocks[0]["score"] == 0.9
    trader._place_order.assert_not_called()


def test_filter_mode_buy_bonus_does_not_create_standalone_buy(monkeypatch) -> None:
    resolver = MagicMock(return_value=_signal("BUY"))
    selector_frame = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "score": 0.9,
                "current_price": 50_000.0,
                "exchange": "KR",
            }
        ]
    )
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter", "buy_score_bonus": 0.2},
        resolver=resolver,
        selector_frame=selector_frame,
    )

    trader.run_daily_routine()

    assert trader.last_top_stocks[0]["score"] == 0.9
    trader._place_order.assert_not_called()


def test_resolver_error_logs_error_signal(monkeypatch, caplog) -> None:
    resolver = MagicMock(side_effect=RuntimeError("fixture 수집 실패"))
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
    )

    with caplog.at_level(logging.INFO):
        trader.run_daily_routine()

    messages = [record.getMessage() for record in caplog.records]
    assert any("signal=ERROR" in message for message in messages)


def test_empty_ticker_skips_smart_money_resolver(monkeypatch) -> None:
    resolver = MagicMock(side_effect=AssertionError("빈 ticker는 분석하지 않습니다."))
    selector_frame = pd.DataFrame(
        [
            {
                "ticker": "",
                "score": 0.5,
                "current_price": 50_000.0,
                "exchange": "KR",
            }
        ]
    )
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
        selector_frame=selector_frame,
    )

    trader.run_daily_routine()

    resolver.assert_not_called()
    assert trader.last_top_stocks[0]["smart_money_signal"] == "SKIPPED"


def test_invalid_selector_score_does_not_crash_candidate_filter(monkeypatch, caplog) -> None:
    resolver = MagicMock(return_value=_signal("HOLD"))
    selector_frame = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "score": "not-a-number",
                "current_price": 50_000.0,
                "exchange": "KR",
            }
        ]
    )
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter", "buy_score_bonus": 0.2},
        resolver=resolver,
        selector_frame=selector_frame,
    )

    with caplog.at_level(logging.WARNING):
        trader.run_daily_routine()

    assert trader.last_top_stocks[0]["score"] == 0.0
    trader._place_order.assert_not_called()
    assert any("selector score" in record.getMessage() for record in caplog.records)


def test_non_finite_selector_score_does_not_pass_buy_gate(monkeypatch, caplog) -> None:
    resolver = MagicMock(return_value=_signal("BUY"))
    selector_frame = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "score": float("nan"),
                "current_price": 50_000.0,
                "exchange": "KR",
            },
            {
                "ticker": "000660",
                "score": float("inf"),
                "current_price": 80_000.0,
                "exchange": "KR",
            },
        ]
    )
    _, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter", "buy_score_bonus": 0.2},
        resolver=resolver,
        selector_frame=selector_frame,
    )

    with caplog.at_level(logging.WARNING):
        trader.run_daily_routine()

    assert [stock["score"] for stock in trader.last_top_stocks] == [0.0, 0.0]
    trader._place_order.assert_not_called()
    assert sum("selector score" in record.getMessage() for record in caplog.records) == 2


def test_holding_smart_money_sell_warns_without_auto_liquidation(monkeypatch, caplog) -> None:
    resolver = MagicMock(return_value=_signal("SELL"))
    position = Position(
        symbol="005930",
        quantity=10,
        avg_price=50_000.0,
        current_price=51_000.0,
        exchange="KR",
    )
    module, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
        positions=[position],
        mock_exit=False,
    )
    monkeypatch.setattr(module, "EXIT_MODULE_AVAILABLE", False)

    with caplog.at_level(logging.WARNING):
        sold_tickers = trader._process_exit_strategies(
            trader.api_client.get_account_balance(),
            current_scores={"005930": 2.0},
        )

    assert sold_tickers == []
    trader._place_order.assert_not_called()
    assert any("Smart Money SELL 보유 경고" in record.getMessage() for record in caplog.records)


def test_stop_loss_runs_before_smart_money_holding_warning(monkeypatch) -> None:
    resolver = MagicMock(
        side_effect=AssertionError("손절 판단 전에 외부 분석을 호출하면 안 됩니다.")
    )
    position = Position(
        symbol="005930",
        quantity=10,
        avg_price=50_000.0,
        current_price=40_000.0,
        exchange="KR",
    )
    module, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
        positions=[position],
        mock_exit=False,
    )
    monkeypatch.setattr(module, "EXIT_MODULE_AVAILABLE", False)

    sold_tickers = trader._process_exit_strategies(
        trader.api_client.get_account_balance(),
        current_scores={"005930": 2.0},
    )

    assert sold_tickers == ["005930"]
    trader._place_order.assert_called_once()
    assert trader._place_order.call_args.args[2] == OrderSide.SELL
    resolver.assert_not_called()


def test_partial_exit_skips_stale_smart_money_holding_warning(monkeypatch) -> None:
    resolver = MagicMock(
        side_effect=AssertionError("부분 청산 후 같은 position으로 경고하면 안 됩니다.")
    )
    position = Position(
        symbol="005930",
        quantity=10,
        avg_price=50_000.0,
        current_price=51_000.0,
        exchange="KR",
    )
    module, trader = _make_trader(
        monkeypatch,
        config_values={"enabled": True, "mode": "filter"},
        resolver=resolver,
        positions=[position],
        mock_exit=False,
    )
    exit_signal = MagicMock()
    exit_signal.should_exit = True
    exit_signal.exit_ratio = 0.5
    exit_signal.reason = "partial test"
    trader.exit_strategy = MagicMock()
    trader.exit_strategy.check_exit.return_value = exit_signal
    monkeypatch.setattr(module, "EXIT_MODULE_AVAILABLE", True)

    sold_tickers = trader._process_exit_strategies(
        trader.api_client.get_account_balance(),
        current_scores={"005930": 2.0},
    )

    assert sold_tickers == []
    trader._place_order.assert_called_once()
    assert trader._place_order.call_args.args[1] == 5
    assert trader._place_order.call_args.args[2] == OrderSide.SELL
    resolver.assert_not_called()
