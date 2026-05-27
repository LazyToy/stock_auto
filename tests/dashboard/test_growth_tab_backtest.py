from datetime import date
from pathlib import Path

import pandas as pd

from dashboard.components.growth_tab import (
    build_growth_backtest_args,
    build_growth_backtest_command,
    fetch_growth_validation_price_history,
    find_latest_backtest_report,
    format_currency_price,
    format_optional_number,
    format_optional_percent,
    format_supply_flow_label,
    format_supply_flow_value,
    growth_validation_results_to_dataframe,
    list_growth_candidate_snapshot_files,
    read_backtest_report_preview,
    run_growth_backtest,
    save_growth_results_for_validation,
    search_growth_stocks_compat,
)
from src.analysis.growth_validation import GrowthCandidateSnapshot, GrowthValidationResult


def test_build_growth_backtest_command_points_to_existing_cli():
    command = build_growth_backtest_command(
        start=date(2026, 4, 1),
        end=date(2026, 4, 30),
        horizons="1,3,5",
        surge_threshold=15,
    )

    assert command == (
        "python -m src.crawling.backtest_early_signal "
        "--start 2026-04-01 --end 2026-04-30 "
        "--horizons 1,3,5 --surge-threshold 15"
    )


def test_build_growth_backtest_args_uses_current_python_entrypoint():
    args = build_growth_backtest_args(
        start=date(2026, 4, 1),
        end=date(2026, 4, 30),
        horizons="1,3,5",
        surge_threshold=15,
    )

    assert Path(args[0]).name.lower().startswith("python")
    assert args[1:] == [
        "-m",
        "src.crawling.backtest_early_signal",
        "--start",
        "2026-04-01",
        "--end",
        "2026-04-30",
        "--horizons",
        "1,3,5",
        "--surge-threshold",
        "15",
    ]


def test_run_growth_backtest_invokes_subprocess_runner_without_shell():
    captured = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_runner(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Result()

    result = run_growth_backtest(
        start=date(2026, 4, 1),
        end=date(2026, 4, 30),
        horizons="1,3,5",
        surge_threshold=15,
        timeout_seconds=12,
        runner=fake_runner,
    )

    assert result.returncode == 0
    assert captured["args"][1:3] == ["-m", "src.crawling.backtest_early_signal"]
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "timeout": 12,
    }


def test_find_latest_backtest_report_returns_newest_file(tmp_path):
    older = tmp_path / "backtest_20260401.md"
    newer = tmp_path / "backtest_20260430.md"
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")

    assert find_latest_backtest_report(tmp_path) == newer
    assert read_backtest_report_preview(newer, max_chars=2) == "ne..."


def test_list_growth_candidate_snapshot_files_returns_latest_first(tmp_path):
    older = tmp_path / "growth_candidates_20260401.csv"
    newer = tmp_path / "growth_candidates_20260501.csv"
    ignored = tmp_path / "other.csv"
    older.write_text("date,symbol,name,score,sector\n", encoding="utf-8")
    newer.write_text("date,symbol,name,score,sector\n", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")

    assert list_growth_candidate_snapshot_files(tmp_path) == [newer, older]


def test_search_growth_stocks_compat_omits_interest_window_for_old_finder():
    class OldFinder:
        def search_growth_stocks(self, *, market, candidate_mode, candidate_limit, prefilter_limit):
            return {
                "market": market,
                "candidate_mode": candidate_mode,
                "candidate_limit": candidate_limit,
                "prefilter_limit": prefilter_limit,
            }

    result = search_growth_stocks_compat(
        OldFinder(),
        market="KR",
        candidate_mode="market",
        candidate_limit=20,
        prefilter_limit=100,
        interest_window_days=60,
    )

    assert result == {
        "market": "KR",
        "candidate_mode": "market",
        "candidate_limit": 20,
        "prefilter_limit": 100,
    }


def test_search_growth_stocks_compat_passes_interest_window_for_new_finder():
    class NewFinder:
        def search_growth_stocks(
            self,
            *,
            market,
            candidate_mode,
            candidate_limit,
            prefilter_limit,
            interest_window_days,
        ):
            return interest_window_days

    assert (
        search_growth_stocks_compat(
            NewFinder(),
            market="US",
            candidate_mode="market",
            candidate_limit=20,
            prefilter_limit=100,
            interest_window_days=60,
        )
        == 60
    )


def test_optional_formatters_tolerate_old_growth_stock_objects():
    class OldStock:
        market_interest_score = 8.123

    stock = OldStock()

    assert format_optional_number(getattr(stock, "financial_growth_score", None)) == "N/A"
    assert format_optional_number(stock.market_interest_score) == "8.1"
    assert format_optional_number(1234567, digits=0) == "1,234,567"
    assert format_optional_percent(getattr(stock, "data_confidence", None)) == "N/A"


def test_format_currency_price_displays_currency_and_thousands():
    assert format_currency_price(1234567, "KRW") == "1,234,567 KRW"
    assert format_currency_price(1234.5, "USD") == "1,234.50 USD"
    assert format_currency_price(None, "USD") == "N/A"


def test_format_supply_flow_value_displays_source_unit():
    assert format_supply_flow_value(6566, "주") == "6,566 주"
    assert format_supply_flow_value(-7593, "주") == "-7,593 주"
    assert format_supply_flow_value(-4982, "KRW") == "-4,982 KRW"
    assert format_supply_flow_value(None, "주") == "N/A"


def test_format_supply_flow_label_makes_unit_visible_from_source():
    assert format_supply_flow_label("5일 스마트머니", "주") == "5일 스마트머니(주)"
    assert format_supply_flow_label("최근 1일 외국인", "", source="naver") == "최근 1일 외국인(주)"
    assert format_supply_flow_label("최근 1일 기관", "", source="pykrx") == "최근 1일 기관(KRW)"


def test_save_growth_results_for_validation_persists_search_results(tmp_path):
    class Stock:
        symbol = "AAA"
        name = "Alpha"
        sector = "Technology"
        growth_score = 8.7

    path = save_growth_results_for_validation(
        [Stock()],
        snapshot_date=date(2026, 5, 1),
        output_dir=tmp_path,
    )

    assert path.name == "growth_candidates_20260501.csv"
    assert "AAA" in path.read_text(encoding="utf-8-sig")


def test_fetch_growth_validation_price_history_resolves_numeric_kr_symbols():
    snapshots = [
        GrowthCandidateSnapshot("2026-05-01", "036540", "SFASemicon", 9.5, "Technology"),
        GrowthCandidateSnapshot("2026-05-01", "AAPL", "Apple", 8.1, "Technology"),
    ]
    empty = pd.DataFrame()
    valid = pd.DataFrame(
        {"Close": [100.0, 105.0]},
        index=pd.date_range("2026-05-01", periods=2, freq="B"),
    )
    calls = []

    def fake_fetcher(symbol, *, start, end):
        calls.append(symbol)
        if symbol == "036540.KQ" or symbol == "AAPL":
            return valid
        return empty

    histories = fetch_growth_validation_price_history(
        snapshots,
        history_fetcher=fake_fetcher,
    )

    assert calls == ["036540.KQ", "AAPL"]
    assert histories["036540"].equals(valid)
    assert histories["AAPL"].equals(valid)


def test_fetch_growth_validation_price_history_falls_back_to_ks_for_kr_symbols():
    snapshots = [
        GrowthCandidateSnapshot("2026-05-01", "019180", "THN", 9.0, "Consumer Cyclical"),
    ]
    empty = pd.DataFrame()
    valid = pd.DataFrame(
        {"Close": [100.0, 102.0]},
        index=pd.date_range("2026-05-01", periods=2, freq="B"),
    )
    calls = []

    def fake_fetcher(symbol, *, start, end):
        calls.append(symbol)
        return valid if symbol == "019180.KS" else empty

    histories = fetch_growth_validation_price_history(
        snapshots,
        history_fetcher=fake_fetcher,
    )

    assert calls == ["019180.KQ", "019180.KS"]
    assert histories["019180"].equals(valid)


def test_growth_validation_results_to_dataframe_uses_display_columns():
    results = [
        GrowthValidationResult(
            date=pd.Timestamp("2026-05-01"),
            symbol="AAA",
            name="Alpha",
            score=8.5,
            sector="Technology",
            return_20d=12.345,
            return_60d=None,
            hit_20d=True,
            hit_60d=False,
        )
    ]

    df = growth_validation_results_to_dataframe(results)

    assert list(df.columns) == [
        "날짜",
        "종목코드",
        "종목명",
        "섹터",
        "점수",
        "20일수익률(%)",
        "20일Hit",
        "60일수익률(%)",
        "60일Hit",
    ]
    assert df.iloc[0].to_dict() == {
        "날짜": "2026-05-01",
        "종목코드": "AAA",
        "종목명": "Alpha",
        "섹터": "Technology",
        "점수": 8.5,
        "20일수익률(%)": 12.35,
        "20일Hit": True,
        "60일수익률(%)": None,
        "60일Hit": False,
    }
