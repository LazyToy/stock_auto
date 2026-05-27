"""Smart Money 백테스트 CLI 테스트."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch


def test_main_writes_fixture_json_report(tmp_path) -> None:
    """fixture 모드에서 네트워크 없이 JSON 백테스트 리포트를 만든다."""
    from scripts import run_smart_money_backtest as module

    output = tmp_path / "backtest.json"
    exit_code = module.main(
        [
            "--symbols",
            "AAPL",
            "--market",
            "US",
            "--fixture",
            "--output",
            str(output),
            "--format",
            "json",
        ],
        clock=lambda: datetime(2024, 1, 2, 9, 30),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["summary"]["total_symbols"] == 1
    assert payload["results"][0]["symbol"] == "AAPL"
    assert "metrics" in payload["results"][0]
    assert payload["results"][0]["metrics"]["total_trades"] > 0
    assert payload["results"][0]["trades"]


def test_fixture_fetcher_loads_stored_csv_fixture() -> None:
    """fixture fetcher는 저장된 CSV OHLCV를 사용한다."""
    from scripts import run_smart_money_backtest as module
    from src.analysis.timeframes import Timeframe

    dataset = module.FixtureSmartMoneyBacktestFetcher().fetch_symbol(
        "AAPL",
        market="US",
        exchange="NASD",
    )

    minute_data = dataset.timeframes[Timeframe.MINUTE_5]
    assert minute_data.source == "fixture-csv:smart_money_backtest_tradeable.csv:5m"
    assert len(minute_data.data) == 23
    assert list(minute_data.data.columns) == ["open", "high", "low", "close", "volume"]


def test_main_returns_error_for_empty_symbol_input(tmp_path) -> None:
    """symbol 입력이 비어 있으면 사용자 입력 오류로 종료한다."""
    from scripts import run_smart_money_backtest as module

    output = tmp_path / "backtest.json"
    exit_code = module.main(["--symbols", " ", "--output", str(output)])

    assert exit_code == 2
    assert not output.exists()


def test_period_configures_live_fetcher_and_payload(tmp_path) -> None:
    """--period 값은 live fetcher 생성과 payload metadata에 함께 반영된다."""
    from scripts import run_smart_money_backtest as module
    from src.analysis.timeframes import MultiTimeframeDataset

    output = tmp_path / "backtest.json"

    with patch.object(module, "MultiTimeframeFetcher") as fetcher_cls:
        fetcher_cls.return_value.fetch_symbol.return_value = MultiTimeframeDataset(
            symbol="AAPL",
            market="US",
            exchange="NASD",
        )
        exit_code = module.main(
            [
                "--symbols",
                "AAPL",
                "--market",
                "US",
                "--period",
                "6mo",
                "--output",
                str(output),
            ],
            clock=lambda: datetime(2024, 1, 2, 9, 30),
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["period"] == "6mo"
    fetcher_cls.assert_called_once_with(daily_lookback_days=186, yfinance_daily_period="6mo")


def test_generated_at_argument_makes_report_timestamp_deterministic(tmp_path) -> None:
    """--generated-at을 지정하면 실행 시각 대신 고정 timestamp를 리포트에 쓴다."""
    from scripts import run_smart_money_backtest as module

    output = tmp_path / "backtest.json"
    exit_code = module.main(
        [
            "--symbols",
            "AAPL",
            "--fixture",
            "--generated-at",
            "2024-01-02T09:30:00+00:00",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["generated_at"] == "2024-01-02T09:30:00+00:00"
