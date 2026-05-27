"""Pure post-validation helpers for growth candidate snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd


@dataclass
class GrowthCandidateSnapshot:
    date: object
    symbol: str
    name: str
    score: float
    sector: str | None = None


@dataclass
class GrowthValidationResult:
    date: pd.Timestamp
    symbol: str
    name: str
    score: float
    sector: str | None
    return_20d: float | None
    return_60d: float | None
    hit_20d: bool
    hit_60d: bool


SNAPSHOT_COLUMNS = ["date", "symbol", "name", "score", "sector"]


def snapshots_from_growth_stocks(
    stocks: list[object],
    *,
    snapshot_date: object,
) -> list[GrowthCandidateSnapshot]:
    """Convert GrowthStock-like objects into validation snapshots."""
    return [
        GrowthCandidateSnapshot(
            date=snapshot_date,
            symbol=str(getattr(stock, "symbol")),
            name=str(getattr(stock, "name")),
            score=float(getattr(stock, "growth_score")),
            sector=getattr(stock, "sector", None),
        )
        for stock in stocks
    ]


def save_growth_candidate_snapshots(
    snapshots: list[GrowthCandidateSnapshot],
    *,
    output_dir: str | Path = "data/growth_candidates",
) -> Path:
    """Persist growth candidate snapshots to a dated CSV file.

    Rows are deduplicated by (date, symbol), keeping the first row. This makes
    repeated clicks in Streamlit idempotent for the same candidate list.
    """
    if not snapshots:
        raise ValueError("snapshots must not be empty")

    snapshot_date = _to_date_timestamp(snapshots[0].date).strftime("%Y%m%d")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"growth_candidates_{snapshot_date}.csv"

    new_df = _snapshots_to_dataframe(snapshots)
    if file_path.exists():
        existing_df = pd.read_csv(file_path, dtype={"date": str, "symbol": str})
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = (
        combined[SNAPSHOT_COLUMNS]
        .drop_duplicates(subset=["date", "symbol"], keep="first")
        .sort_values(["date", "score", "symbol"], ascending=[True, False, True])
    )
    combined.to_csv(file_path, index=False, encoding="utf-8-sig")
    return file_path


def load_growth_candidate_snapshots(path: str | Path) -> list[GrowthCandidateSnapshot]:
    """Load saved growth candidate snapshots from a CSV file."""
    df = pd.read_csv(path, dtype={"date": str, "symbol": str}).fillna("")
    snapshots: list[GrowthCandidateSnapshot] = []
    for record in df.to_dict("records"):
        snapshots.append(
            GrowthCandidateSnapshot(
                date=str(record["date"]),
                symbol=str(record["symbol"]),
                name=str(record["name"]),
                score=float(record["score"]),
                sector=str(record["sector"]) or None,
            )
        )
    return snapshots


def validate_growth_candidates(
    snapshots: list[GrowthCandidateSnapshot],
    price_history_by_symbol: Mapping[str, pd.DataFrame],
    *,
    hit_threshold: float = 10.0,
) -> list[GrowthValidationResult]:
    results: list[GrowthValidationResult] = []

    for snapshot in snapshots:
        snapshot_date = _to_date_timestamp(snapshot.date)
        close = _close_series(price_history_by_symbol.get(snapshot.symbol))
        entry_pos = _entry_position(close, snapshot_date)
        return_20d = _horizon_return(close, entry_pos, 20)
        return_60d = _horizon_return(close, entry_pos, 60)

        results.append(
            GrowthValidationResult(
                date=snapshot_date,
                symbol=snapshot.symbol,
                name=snapshot.name,
                score=snapshot.score,
                sector=snapshot.sector,
                return_20d=return_20d,
                return_60d=return_60d,
                hit_20d=return_20d is not None and return_20d >= hit_threshold,
                hit_60d=return_60d is not None and return_60d >= hit_threshold,
            )
        )

    return results


def _snapshots_to_dataframe(snapshots: list[GrowthCandidateSnapshot]) -> pd.DataFrame:
    rows = []
    for snapshot in snapshots:
        rows.append(
            {
                "date": _to_date_timestamp(snapshot.date).strftime("%Y-%m-%d"),
                "symbol": snapshot.symbol,
                "name": snapshot.name,
                "score": snapshot.score,
                "sector": snapshot.sector or "",
            }
        )
    return pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)


def summarize_validation(results: list[GrowthValidationResult]) -> dict[str, float | int]:
    returns_20d = [result.return_20d for result in results if result.return_20d is not None]
    returns_60d = [result.return_60d for result in results if result.return_60d is not None]

    return {
        "total": len(results),
        "hit_rate_20d": _hit_rate(results, "20d"),
        "hit_rate_60d": _hit_rate(results, "60d"),
        "avg_return_20d": _average(returns_20d),
        "avg_return_60d": _average(returns_60d),
    }


def _to_date_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value).normalize()
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp


def _close_series(history: pd.DataFrame | None) -> pd.Series:
    if history is None or history.empty or "Close" not in history.columns:
        return pd.Series(dtype=float)

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        return pd.Series(dtype=float)

    close = close.copy()
    index = pd.DatetimeIndex(pd.to_datetime(close.index)).normalize()
    if index.tz is not None:
        index = index.tz_localize(None)
    close.index = index
    return close.sort_index()


def _entry_position(close: pd.Series, snapshot_date: pd.Timestamp) -> int | None:
    if close.empty:
        return None
    position = int(close.index.searchsorted(snapshot_date, side="left"))
    if position >= len(close):
        return None
    return position


def _horizon_return(close: pd.Series, entry_pos: int | None, horizon: int) -> float | None:
    if entry_pos is None:
        return None
    target_pos = entry_pos + horizon
    if target_pos >= len(close):
        return None

    entry = float(close.iloc[entry_pos])
    if entry == 0:
        return None
    target = float(close.iloc[target_pos])
    return round((target / entry - 1.0) * 100.0, 10)


def _hit_rate(results: list[GrowthValidationResult], horizon: str) -> float:
    if horizon == "20d":
        valid = [result for result in results if result.return_20d is not None]
        hits = sum(1 for result in valid if result.hit_20d)
    else:
        valid = [result for result in results if result.return_60d is not None]
        hits = sum(1 for result in valid if result.hit_60d)
    return hits / len(valid) if valid else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
