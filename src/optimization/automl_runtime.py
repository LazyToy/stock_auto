"""Runtime helpers for using AutoML results without touching order execution."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def save_automl_result(result: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    """Persist an AutoML result as a reusable advisory artifact."""
    root = Path(base_dir or ".")
    output_dir = root / "data" / "automl_params"
    output_dir.mkdir(parents=True, exist_ok=True)

    symbol = _clean_symbol(result.get("resolved_symbol") or result.get("symbol") or "UNKNOWN")
    strategy_type = str(result.get("strategy_type") or "UNKNOWN").lower()
    path = output_dir / f"{symbol}_{strategy_type}.json"

    payload = {
        **result,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_automl_artifacts(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Load valid AutoML result JSON files and skip invalid artifacts."""
    artifacts: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            artifacts.append(payload)
    return artifacts


def load_automl_artifacts_from_dir(directory: str | Path) -> list[dict[str, Any]]:
    """Load every AutoML artifact from a directory."""
    path = Path(directory)
    if not path.exists() or not path.is_dir():
        return []
    return load_automl_artifacts(sorted(path.glob("*.json")))


def apply_automl_candidate_adjustment(
    candidates: pd.DataFrame,
    artifacts: list[dict[str, Any]],
    *,
    min_fitness: float = 0.0,
    max_bonus: float = 0.2,
) -> pd.DataFrame:
    """
    Add advisory AutoML columns and a bounded score bonus to matching candidates.

    This does not create new candidates and never issues orders; it only nudges
    existing selector scores when an artifact clears the configured threshold.
    """
    if candidates.empty or not artifacts:
        return candidates

    artifact_by_symbol = _select_best_artifacts_by_symbol(artifacts)
    adjusted = candidates.copy()
    for column in ["automl_strategy", "automl_fitness", "automl_validation_fitness", "automl_bonus"]:
        if column not in adjusted.columns:
            adjusted[column] = pd.NA

    for idx, row in adjusted.iterrows():
        symbol = _clean_symbol(row.get("ticker") or row.get("symbol"))
        artifact = artifact_by_symbol.get(symbol)
        if not artifact:
            continue
        if not _passes_overfit_guard(artifact):
            continue

        fitness = _coerce_float(artifact.get("best_fitness"))
        validation_fitness = _validation_fitness(artifact)
        effective_fitness = validation_fitness if validation_fitness is not None else fitness
        if effective_fitness is None or effective_fitness < min_fitness:
            continue

        current_score = _coerce_float(row.get("score")) or 0.0
        bonus = min(max_bonus, max(0.0, effective_fitness) * max_bonus)
        adjusted.loc[idx, "score"] = round(current_score + bonus, 10)
        adjusted.loc[idx, "automl_strategy"] = artifact.get("strategy_type")
        adjusted.loc[idx, "automl_fitness"] = fitness
        adjusted.loc[idx, "automl_validation_fitness"] = validation_fitness
        adjusted.loc[idx, "automl_bonus"] = bonus

    return adjusted


def _select_best_artifacts_by_symbol(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not _passes_overfit_guard(artifact):
            continue
        for symbol in _artifact_symbol_keys(artifact):
            if (
                symbol not in selected
                or _artifact_score(artifact) > _artifact_score(selected[symbol])
            ):
                selected[symbol] = artifact
    return selected


def _artifact_score(artifact: dict[str, Any]) -> float:
    validation_fitness = _validation_fitness(artifact)
    fitness = _coerce_float(artifact.get("best_fitness"))
    value = validation_fitness if validation_fitness is not None else fitness
    return value if value is not None else float("-inf")


def _passes_overfit_guard(artifact: dict[str, Any]) -> bool:
    validation = artifact.get("validation")
    if not isinstance(validation, dict):
        return True
    guard = validation.get("overfit_guard")
    if not isinstance(guard, dict):
        return True
    return guard.get("passes") is not False


def _validation_fitness(artifact: dict[str, Any]) -> float | None:
    validation = artifact.get("validation")
    if not isinstance(validation, dict):
        return None

    aggregate = validation.get("aggregate")
    if isinstance(aggregate, dict):
        value = _coerce_float(aggregate.get("average_test_fitness"))
        if value is not None:
            return value

    test = validation.get("test")
    if isinstance(test, dict):
        return _coerce_float(test.get("fitness"))
    return None


def _clean_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _artifact_symbol_keys(artifact: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ["requested_symbol", "resolved_symbol", "symbol"]:
        value = _clean_symbol(artifact.get(field))
        for key in _symbol_aliases(value):
            if key and key not in keys:
                keys.append(key)
    return keys


def _symbol_aliases(symbol: str) -> list[str]:
    if not symbol:
        return []
    aliases = [symbol]
    for suffix in [".KS", ".KQ"]:
        if symbol.endswith(suffix):
            aliases.append(symbol[: -len(suffix)])
    return aliases


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None
