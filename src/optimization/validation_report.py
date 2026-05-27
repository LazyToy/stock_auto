"""Multi-symbol AutoML validation reporting helpers."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


def build_multi_symbol_validation_report(
    results: list[dict[str, Any]],
    requested_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize and rank AutoML validation results across symbols."""
    entries = [_build_report_entry(result) for result in results if isinstance(result, dict)]
    skipped_results = [
        _build_skipped_entry(result)
        for result in results
        if isinstance(result, dict) and result.get("status") == "skipped"
    ]
    ranked_results = [entry for entry in entries if entry["validation_fitness"] is not None]
    ranked_results.sort(
        key=lambda entry: (
            bool(entry["usable"]),
            _sort_number(entry["validation_fitness"]),
            _sort_number(entry["stability_score"]),
        ),
        reverse=True,
    )

    validation_scores = [
        entry["validation_fitness"]
        for entry in ranked_results
        if entry["validation_fitness"] is not None
    ]
    usable_scores = [
        entry["validation_fitness"]
        for entry in ranked_results
        if entry["usable"] and entry["validation_fitness"] is not None
    ]
    usable_entries = [entry for entry in ranked_results if entry["usable"]]
    requested = _normalize_symbols(requested_symbols)
    observed = _observed_symbols(entries)
    missing_symbols = [symbol for symbol in requested if symbol not in observed]
    symbol_count = len(requested) if requested else len(results)

    return {
        "symbol_count": symbol_count,
        "result_count": len(results),
        "validated_symbol_count": len(ranked_results),
        "skipped_symbol_count": len(skipped_results),
        "missing_symbol_count": len(missing_symbols),
        "guard_pass_count": sum(1 for entry in ranked_results if entry["overfit_guard_passes"]),
        "guard_fail_count": sum(1 for entry in ranked_results if not entry["overfit_guard_passes"]),
        "average_validation_fitness": _average(validation_scores),
        "average_usable_validation_fitness": _average(usable_scores),
        "best_usable_symbol": usable_entries[0]["symbol"] if usable_entries else None,
        "best_usable_validation_fitness": (
            usable_entries[0]["validation_fitness"] if usable_entries else None
        ),
        "ranked_results": ranked_results,
        "skipped_results": skipped_results,
        "missing_symbols": missing_symbols,
    }


def save_multi_symbol_validation_report(
    report: dict[str, Any],
    base_dir: str | Path | None = None,
) -> Path:
    """Persist a multi-symbol AutoML validation report as JSON."""
    root = Path(base_dir or ".")
    output_dir = root / "data" / "automl_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = output_dir / f"multi_symbol_automl_report_{timestamp}.json"
    payload = {
        **report,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _build_report_entry(result: dict[str, Any]) -> dict[str, Any]:
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    guard = validation.get("overfit_guard") if isinstance(validation, dict) else None
    guard_passes = _guard_passes(guard)
    failed_checks = _failed_checks(guard)
    validation_fitness = _validation_fitness(validation)
    stability_score = _stability_score(validation)
    test_trade_count = _test_trade_count(validation)

    return {
        "symbol": str(result.get("resolved_symbol") or result.get("symbol") or ""),
        "requested_symbol": result.get("requested_symbol"),
        "resolved_symbol": result.get("resolved_symbol"),
        "strategy_type": result.get("strategy_type") or result.get("strategy"),
        "best_fitness": _coerce_finite_float(result.get("best_fitness")),
        "validation_method": validation.get("method") if isinstance(validation, dict) else None,
        "validation_fitness": validation_fitness,
        "stability_score": stability_score,
        "test_trade_count": test_trade_count,
        "overfit_guard_passes": guard_passes,
        "overfit_failed_checks": failed_checks,
        "deflated_sharpe": _deflated_sharpe(guard),
        "usable": bool(validation_fitness is not None and guard_passes),
    }


def _build_skipped_entry(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(result.get("requested_symbol") or result.get("symbol") or ""),
        "resolved_symbol": result.get("resolved_symbol"),
        "status": "skipped",
        "error": result.get("error"),
    }


def _validation_fitness(validation: dict[str, Any]) -> float | None:
    aggregate = validation.get("aggregate")
    if isinstance(aggregate, dict):
        value = _coerce_finite_float(aggregate.get("average_test_fitness"))
        if value is not None:
            return value

    test = validation.get("test")
    if isinstance(test, dict):
        return _coerce_finite_float(test.get("fitness"))
    return None


def _stability_score(validation: dict[str, Any]) -> float | None:
    aggregate = validation.get("aggregate")
    if isinstance(aggregate, dict):
        return _coerce_finite_float(aggregate.get("stability_score"))
    return None


def _test_trade_count(validation: dict[str, Any]) -> float | None:
    test = validation.get("test")
    if isinstance(test, dict):
        metrics = test.get("metrics")
        if isinstance(metrics, dict):
            value = _coerce_finite_float(metrics.get("trade_count"))
            if value is not None:
                return value

    guard = validation.get("overfit_guard")
    if isinstance(guard, dict):
        return _coerce_finite_float(guard.get("min_test_trades"))
    return None


def _guard_passes(guard: Any) -> bool:
    if not isinstance(guard, dict):
        return True
    return guard.get("passes") is not False


def _failed_checks(guard: Any) -> list[str]:
    if not isinstance(guard, dict):
        return []
    checks = guard.get("failed_checks")
    if not isinstance(checks, list):
        return []
    return [str(check) for check in checks]


def _deflated_sharpe(guard: Any) -> float | None:
    if not isinstance(guard, dict):
        return None
    return _coerce_finite_float(guard.get("deflated_sharpe"))


def _normalize_symbols(symbols: list[str] | None) -> list[str]:
    if not symbols:
        return []
    normalized: list[str] = []
    for symbol in symbols:
        value = str(symbol or "").strip().upper()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _observed_symbols(entries: list[dict[str, Any]]) -> list[str]:
    symbols: list[str] = []
    for entry in entries:
        for key in ["symbol", "requested_symbol", "resolved_symbol"]:
            value = str(entry.get(key) or "").strip().upper()
            if value and value not in symbols:
                symbols.append(value)
    return symbols


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 10)


def _sort_number(value: Any) -> float:
    number = _coerce_finite_float(value)
    return number if number is not None else float("-inf")


def _coerce_finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None
