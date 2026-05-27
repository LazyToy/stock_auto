import pandas as pd

from src.analysis.growth_validation import (
    GrowthCandidateSnapshot,
    load_growth_candidate_snapshots,
    save_growth_candidate_snapshots,
    snapshots_from_growth_stocks,
    validate_growth_candidates,
    summarize_validation,
)


def _history(start: str, closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=dates)


def test_validate_growth_candidates_uses_first_trading_day_after_snapshot():
    snapshots = [
        GrowthCandidateSnapshot(
            date="2026-05-02",
            symbol="AAA",
            name="Alpha",
            score=8.5,
            sector="Technology",
        )
    ]
    closes = [100.0] * 80
    closes[3] = 100.0
    closes[23] = 112.0
    closes[63] = 95.0
    histories = {"AAA": _history("2026-04-29", closes)}

    result = validate_growth_candidates(snapshots, histories, hit_threshold=10.0)[0]

    assert result.date == pd.Timestamp("2026-05-02")
    assert result.symbol == "AAA"
    assert result.name == "Alpha"
    assert result.score == 8.5
    assert result.sector == "Technology"
    assert result.return_20d == 12.0
    assert result.return_60d == -5.0
    assert result.hit_20d is True
    assert result.hit_60d is False


def test_validate_growth_candidates_marks_missing_horizons_as_not_hit():
    snapshots = [
        GrowthCandidateSnapshot(
            date=pd.Timestamp("2026-05-01"),
            symbol="SHORT",
            name="Short History",
            score=6.0,
        ),
        GrowthCandidateSnapshot(
            date=pd.Timestamp("2026-05-01"),
            symbol="MISSING",
            name="Missing History",
            score=5.0,
        ),
    ]
    histories = {"SHORT": _history("2026-05-04", [100.0] + [101.0] * 20)}

    results = validate_growth_candidates(snapshots, histories)

    short = results[0]
    missing = results[1]
    assert short.return_20d == 1.0
    assert short.return_60d is None
    assert short.hit_20d is False
    assert short.hit_60d is False
    assert missing.return_20d is None
    assert missing.return_60d is None
    assert missing.hit_20d is False
    assert missing.hit_60d is False


def test_summarize_validation_excludes_missing_returns_from_averages_and_rates():
    snapshots = [
        GrowthCandidateSnapshot("2026-05-01", "WIN", "Winner", 9.0),
        GrowthCandidateSnapshot("2026-05-01", "MISS", "Miss", 7.0),
        GrowthCandidateSnapshot("2026-05-01", "SHORT", "Short", 6.0),
    ]
    histories = {
        "WIN": _history("2026-05-04", [100.0] + [100.0] * 19 + [115.0] + [100.0] * 39 + [130.0]),
        "MISS": _history("2026-05-04", [100.0] + [100.0] * 19 + [105.0] + [100.0] * 39 + [95.0]),
        "SHORT": _history("2026-05-04", [100.0] + [100.0] * 20),
    }

    summary = summarize_validation(
        validate_growth_candidates(snapshots, histories, hit_threshold=10.0)
    )

    assert summary == {
        "total": 3,
        "hit_rate_20d": 1 / 3,
        "hit_rate_60d": 1 / 2,
        "avg_return_20d": (15.0 + 5.0 + 0.0) / 3,
        "avg_return_60d": (30.0 - 5.0) / 2,
    }


def test_snapshots_from_growth_stocks_uses_current_result_fields():
    class Stock:
        symbol = "AAA"
        name = "Alpha"
        sector = "Technology"
        growth_score = 8.7

    snapshots = snapshots_from_growth_stocks([Stock()], snapshot_date="2026-05-01")

    assert snapshots == [
        GrowthCandidateSnapshot(
            date="2026-05-01",
            symbol="AAA",
            name="Alpha",
            score=8.7,
            sector="Technology",
        )
    ]


def test_save_and_load_growth_candidate_snapshots_deduplicates_by_date_symbol(tmp_path):
    snapshots = [
        GrowthCandidateSnapshot("2026-05-01", "AAA", "Alpha", 8.7, "Technology"),
        GrowthCandidateSnapshot("2026-05-01", "AAA", "Alpha Duplicate", 7.0, "Technology"),
        GrowthCandidateSnapshot("2026-05-01", "BBB", "Beta", 7.5, "Healthcare"),
    ]

    path = save_growth_candidate_snapshots(snapshots, output_dir=tmp_path)
    loaded = load_growth_candidate_snapshots(path)

    assert path.name == "growth_candidates_20260501.csv"
    assert loaded == [
        GrowthCandidateSnapshot(
            date="2026-05-01",
            symbol="AAA",
            name="Alpha",
            score=8.7,
            sector="Technology",
        ),
        GrowthCandidateSnapshot(
            date="2026-05-01",
            symbol="BBB",
            name="Beta",
            score=7.5,
            sector="Healthcare",
        ),
    ]
