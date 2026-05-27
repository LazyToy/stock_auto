import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

from src.optimization.validation_report import (
    build_multi_symbol_validation_report,
    save_multi_symbol_validation_report,
)


def normalize_automl_symbol(symbol: str) -> tuple[str, list[str]]:
    """AutoML 가격 조회에 사용할 심볼과 후보 목록을 정규화한다."""
    cleaned_symbol = (symbol or "").strip().upper()
    if not cleaned_symbol:
        return "", []

    if cleaned_symbol.isdigit():
        return cleaned_symbol, [f"{cleaned_symbol}.KS", f"{cleaned_symbol}.KQ"]

    return cleaned_symbol, [cleaned_symbol]


def configure_yfinance_cache(yf_module: Any, base_dir: str | None = None) -> str:
    """yfinance 타임존 캐시를 작업 디렉터리 안으로 고정한다."""
    cache_dir = Path(base_dir or os.getcwd()) / ".cache" / "yfinance"
    cache_dir.mkdir(parents=True, exist_ok=True)

    set_cache_location = getattr(yf_module, "set_tz_cache_location", None)
    if callable(set_cache_location):
        set_cache_location(str(cache_dir))

    return str(cache_dir)


def download_automl_price_history(
    symbol: str,
    period: str = "1y",
    yf_module: Any | None = None,
    base_dir: str | None = None,
) -> tuple[pd.DataFrame, str | None, str | None]:
    """AutoML용 가격 데이터를 내려받고, 실패 시 사용자용 메시지를 반환한다."""
    cleaned_symbol, symbol_candidates = normalize_automl_symbol(symbol)
    if not cleaned_symbol:
        return pd.DataFrame(), None, "종목 코드를 입력하세요."

    if yf_module is None:
        import yfinance as yf_module

    configure_yfinance_cache(yf_module, base_dir=base_dir)

    last_error = None
    for candidate in symbol_candidates:
        try:
            ticker_data = yf_module.Ticker(candidate)
            df = ticker_data.history(period=period)
        except Exception as exc:  # pragma: no cover - 외부 라이브러리 예외 방어
            last_error = exc
            continue

        if isinstance(df, pd.DataFrame) and not df.empty:
            return df, candidate, None

    if last_error is not None and "Empty ticker name" in str(last_error):
        return pd.DataFrame(), None, "종목 코드를 입력하세요."

    return (
        pd.DataFrame(),
        None,
        f"종목 {cleaned_symbol}의 가격 데이터를 가져올 수 없습니다. 종목 코드를 확인하세요.",
    )


def extract_fitness_history(logbook: Any, fallback_fitness: float | None = None) -> list[float]:
    """DEAP logbook에서 차트 표시용 fitness 이력을 float 리스트로 추출한다."""
    raw_history: list[Any] = []

    if logbook:
        if hasattr(logbook, "select"):
            try:
                raw_history = list(logbook.select("max"))
            except Exception:
                raw_history = []
        else:
            try:
                raw_history = [
                    record.get("max") if hasattr(record, "get") else record["max"]
                    for record in logbook
                ]
            except Exception:
                raw_history = []

    history: list[float] = []
    for value in raw_history:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue

        if math.isfinite(numeric_value):
            history.append(numeric_value)

    if history:
        return history

    if fallback_fitness is None:
        return []

    try:
        numeric_fitness = float(fallback_fitness)
    except (TypeError, ValueError):
        return []

    if not math.isfinite(numeric_fitness):
        return []

    return [numeric_fitness]


def summarize_validation_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """여러 종목 AutoML 검증 결과를 평균 test fitness 기준으로 요약한다."""
    symbol_scores: list[tuple[str, float]] = []

    for result in results:
        validation = result.get("validation") if isinstance(result, dict) else None
        if not isinstance(validation, dict):
            continue

        score = None
        aggregate = validation.get("aggregate")
        if isinstance(aggregate, dict):
            score = aggregate.get("average_test_fitness")

        test = validation.get("test")
        if score is None and isinstance(test, dict):
            score = test.get("fitness")

        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(numeric_score):
            continue

        symbol = str(result.get("symbol") or result.get("resolved_symbol") or "")
        symbol_scores.append((symbol, numeric_score))

    if not symbol_scores:
        return {
            "symbol_count": 0,
            "average_test_fitness": 0.0,
            "best_symbol": None,
            "best_test_fitness": None,
        }

    best_symbol, best_score = max(symbol_scores, key=lambda item: item[1])
    average_score = sum(score for _, score in symbol_scores) / len(symbol_scores)

    return {
        "symbol_count": len(symbol_scores),
        "average_test_fitness": float(average_score),
        "best_symbol": best_symbol,
        "best_test_fitness": float(best_score),
    }


def build_fitness_chart_data(
    history: list[float],
    validation: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Fitness evolution 그래프에 validation 기준선을 함께 그릴 long-form 데이터를 만든다."""
    rows: list[dict[str, float | int | str]] = []

    for generation, fitness in enumerate(history):
        rows.append(
            {
                "Generation": generation,
                "Fitness": float(fitness),
                "Series": "Evolution best",
            }
        )

    if not history or not isinstance(validation, dict):
        return pd.DataFrame(rows)

    method = str(validation.get("method", "")).lower()
    if _append_generation_validation_curves(rows, validation.get("generation_history"), method):
        return pd.DataFrame(rows)

    if method == "train_test":
        train = validation.get("train")
        test = validation.get("test")
        train_fitness = _extract_validation_fitness(train)
        test_fitness = _extract_validation_fitness(test)
        if train_fitness is not None:
            rows.extend(_flat_validation_line(history, train_fitness, "Validation train"))
        if test_fitness is not None:
            rows.extend(_flat_validation_line(history, test_fitness, "Validation test"))
    elif method == "walk_forward":
        aggregate = validation.get("aggregate")
        fitness = None
        if isinstance(aggregate, dict):
            fitness = aggregate.get("average_test_fitness")
        average_fitness = _coerce_finite_float(fitness)
        if average_fitness is not None:
            rows.extend(_flat_validation_line(history, average_fitness, "Walk-forward test avg"))

    return pd.DataFrame(rows)


def _append_generation_validation_curves(
    rows: list[dict[str, float | int | str]],
    generation_history: Any,
    method: str,
) -> bool:
    if not isinstance(generation_history, list):
        return False

    added = False
    for index, record in enumerate(generation_history):
        if not isinstance(record, dict):
            continue
        generation = _coerce_generation(record.get("generation"), index)
        if method == "train_test":
            added = _append_generation_point(
                rows,
                generation,
                record.get("train_fitness"),
                "Validation train",
            ) or added
            added = _append_generation_point(
                rows,
                generation,
                record.get("test_fitness"),
                "Validation test",
            ) or added
        elif method == "walk_forward":
            added = _append_generation_point(
                rows,
                generation,
                record.get("average_test_fitness"),
                "Walk-forward test avg",
            ) or added

    return added


def _append_generation_point(
    rows: list[dict[str, float | int | str]],
    generation: int,
    fitness: Any,
    label: str,
) -> bool:
    numeric_fitness = _coerce_finite_float(fitness)
    if numeric_fitness is None:
        return False
    rows.append(
        {
            "Generation": generation,
            "Fitness": numeric_fitness,
            "Series": label,
        }
    )
    return True


def _flat_validation_line(
    history: list[float],
    fitness: float,
    label: str,
) -> list[dict[str, float | int | str]]:
    return [
        {
            "Generation": generation,
            "Fitness": float(fitness),
            "Series": label,
        }
        for generation in range(len(history))
    ]


def _extract_validation_fitness(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    return _coerce_finite_float(value.get("fitness"))


def _coerce_finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None


def _coerce_generation(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
