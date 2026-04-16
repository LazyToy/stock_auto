import math
import os
from pathlib import Path
from typing import Any

import pandas as pd


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
