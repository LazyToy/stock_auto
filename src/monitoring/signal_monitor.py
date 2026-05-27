"""Advisory AutoML signal monitoring helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, MutableSet
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.optimization.evaluator import StrategyEvaluator
from src.optimization.strategy_registry import get_strategy_spec, normalize_strategy_type

logger = logging.getLogger(__name__)

STATE_NAMESPACE = "automl_signal_alerts"
SUPPORTED_ACTIONS = {"BUY", "SELL"}


@dataclass(frozen=True)
class AutomlSignal:
    """A detected AutoML advisory signal."""

    symbol: str
    resolved_symbol: str
    strategy_type: str
    action: str
    timestamp: str
    price: float
    best_fitness: float | None = None
    validation_fitness: float | None = None


@dataclass(frozen=True)
class SignalDispatchResult:
    """Result of one advisory signal notification attempt."""

    signal: AutomlSignal
    sent: bool
    reason: str


class SignalAlertStateStore:
    """Small JSON state store used to avoid repeated alerts."""

    def __init__(self, path: str | Path = Path("data") / "automl_signal_alert_state.json") -> None:
        self.path = Path(path)

    def load(self) -> set[str]:
        """Load sent signal state keys."""
        if not self.path.exists():
            return set()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load AutoML signal alert state: %s", exc)
            return set()
        values = payload.get(STATE_NAMESPACE, []) if isinstance(payload, dict) else []
        if not isinstance(values, list):
            return set()
        return {str(value) for value in values if str(value).strip()}

    def save(self, state: Iterable[str]) -> bool:
        """Persist sent signal state keys without touching secrets or credentials."""
        payload = {STATE_NAMESPACE: sorted({str(value) for value in state if str(value).strip()})}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.warning("Could not save AutoML signal alert state: %s", exc)
            return False


class AutomlSignalMonitor:
    """Scan AutoML artifacts against recent price history and send advisory alerts."""

    def __init__(
        self,
        artifacts: list[dict[str, Any]],
        *,
        history_fetcher: Callable[[str, str], pd.DataFrame] | Any,
        notifier: Callable[[str], bool | None],
        evaluator: StrategyEvaluator | None = None,
        period: str = "1y",
        notify_on: Iterable[str] = ("BUY", "SELL"),
        state_store: SignalAlertStateStore | None = None,
        state: MutableSet[str] | None = None,
    ) -> None:
        self.artifacts = [artifact for artifact in artifacts if isinstance(artifact, dict)]
        self.history_fetcher = history_fetcher
        self.notifier = notifier
        self.evaluator = evaluator or StrategyEvaluator(use_regime_filter=False)
        self.period = str(period or "1y")
        self.notify_on = {
            str(action).strip().upper()
            for action in notify_on
            if str(action).strip().upper() in SUPPORTED_ACTIONS
        }
        self.state_store = state_store
        self.state = state if state is not None else (
            state_store.load() if state_store is not None else set()
        )

    def scan_once(self, symbols: Iterable[str] | None = None) -> list[SignalDispatchResult]:
        """Fetch watchlist data once and dispatch newly detected BUY/SELL alerts."""
        artifacts_by_symbol = _select_best_artifacts_by_symbol(self.artifacts)
        watchlist = _normalize_watchlist(symbols) or sorted(artifacts_by_symbol)
        results: list[SignalDispatchResult] = []

        for symbol in watchlist:
            artifact = artifacts_by_symbol.get(symbol)
            if artifact is None:
                continue
            fetch_symbol = _artifact_resolved_symbol(artifact) or symbol
            try:
                frame = _fetch_history(self.history_fetcher, fetch_symbol, self.period)
                signal = self.build_signal(symbol, artifact, frame)
            except Exception as exc:
                logger.warning("AutoML signal scan failed for %s: %s", symbol, exc)
                continue
            if signal is None or signal.action not in self.notify_on:
                continue

            state_key = build_signal_state_key(signal)
            if state_key in self.state:
                continue

            message = format_automl_signal_message(signal)
            try:
                notify_result = self.notifier(message)
                sent = True if notify_result is None else bool(notify_result)
            except Exception as exc:
                logger.warning("AutoML signal notifier failed for %s: %s", signal.resolved_symbol, exc)
                sent = False
            results.append(
                SignalDispatchResult(
                    signal=signal,
                    sent=sent,
                    reason="sent" if sent else "notifier_failed",
                )
            )
            if sent:
                self.state.add(state_key)
                if self.state_store is not None:
                    self.state_store.save(self.state)

        return results

    def build_signal(
        self,
        requested_symbol: str,
        artifact: dict[str, Any],
        frame: pd.DataFrame,
    ) -> AutomlSignal | None:
        """Build the latest signal for one artifact and price frame."""
        if frame is None or frame.empty:
            return None

        strategy_type = normalize_strategy_type(str(artifact.get("strategy_type") or artifact.get("strategy")))
        params = _artifact_params(artifact, strategy_type)
        if not params:
            return None

        events = self.evaluator.build_signal_events(frame, params, strategy_type=strategy_type)
        if events.empty:
            return None
        latest_event = int(events.reindex(frame.index).fillna(0).iloc[-1])
        action = _event_action(latest_event)
        if action is None:
            return None

        close = _close_series(frame)
        if close.empty:
            return None
        timestamp = str(frame.index[-1])
        return AutomlSignal(
            symbol=str(requested_symbol or _artifact_primary_symbol(artifact)).strip().upper(),
            resolved_symbol=_artifact_resolved_symbol(artifact) or str(requested_symbol).strip().upper(),
            strategy_type=strategy_type,
            action=action,
            timestamp=timestamp,
            price=float(close.iloc[-1]),
            best_fitness=_coerce_float(artifact.get("best_fitness")),
            validation_fitness=_validation_fitness(artifact),
        )


def format_automl_signal_message(signal: AutomlSignal) -> str:
    """Format an advisory-only alert message."""
    validation = (
        f" | validation={signal.validation_fitness:.4f}"
        if signal.validation_fitness is not None
        else ""
    )
    fitness = f"fitness={signal.best_fitness:.4f}" if signal.best_fitness is not None else "fitness=n/a"
    return (
        f"[AutoML Signal] {signal.action} {signal.resolved_symbol}\n"
        f"Strategy: {signal.strategy_type}\n"
        f"Time: {signal.timestamp}\n"
        f"Price: {signal.price:.4f}\n"
        f"{fitness}{validation}\n"
        "This is advisory only; no order was placed."
    )


def build_signal_state_key(signal: AutomlSignal) -> str:
    """Build a stable duplicate-alert key."""
    return f"{signal.resolved_symbol}:{signal.strategy_type}:{signal.timestamp}:{signal.action}"


def _fetch_history(fetcher: Callable[[str, str], pd.DataFrame] | Any, symbol: str, period: str) -> pd.DataFrame:
    if callable(fetcher):
        return fetcher(symbol, period)
    return fetcher.fetch_history(symbol, period=period)


def _select_best_artifacts_by_symbol(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not _passes_overfit_guard(artifact):
            continue
        for symbol in _artifact_symbol_keys(artifact):
            if symbol not in selected or _artifact_score(artifact) > _artifact_score(selected[symbol]):
                selected[symbol] = artifact
    return selected


def _artifact_params(artifact: dict[str, Any], strategy_type: str) -> list[float]:
    raw_params = artifact.get("best_params")
    if isinstance(raw_params, list):
        return [float(value) for value in raw_params]
    if isinstance(raw_params, tuple):
        return [float(value) for value in raw_params]

    best_parameters = artifact.get("best_parameters")
    if not isinstance(best_parameters, dict):
        return []
    labels = get_strategy_spec(strategy_type).parameter_labels
    try:
        return [float(best_parameters[label]) for label in labels]
    except KeyError:
        return []


def _artifact_symbol_keys(artifact: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ["requested_symbol", "resolved_symbol", "symbol"]:
        value = str(artifact.get(field) or "").strip().upper()
        for alias in _symbol_aliases(value):
            if alias and alias not in keys:
                keys.append(alias)
    return keys


def _artifact_primary_symbol(artifact: dict[str, Any]) -> str:
    return str(
        artifact.get("requested_symbol")
        or artifact.get("symbol")
        or artifact.get("resolved_symbol")
        or ""
    ).strip().upper()


def _artifact_resolved_symbol(artifact: dict[str, Any]) -> str:
    return str(
        artifact.get("resolved_symbol")
        or artifact.get("symbol")
        or artifact.get("requested_symbol")
        or ""
    ).strip().upper()


def _symbol_aliases(symbol: str) -> list[str]:
    if not symbol:
        return []
    aliases = [symbol]
    for suffix in [".KS", ".KQ"]:
        if symbol.endswith(suffix):
            aliases.append(symbol[: -len(suffix)])
    return aliases


def _normalize_watchlist(symbols: Iterable[str] | None) -> list[str]:
    if symbols is None:
        return []
    normalized: list[str] = []
    for symbol in symbols:
        value = str(symbol or "").strip().upper()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _event_action(value: int) -> str | None:
    if value > 0:
        return "BUY"
    if value < 0:
        return "SELL"
    return None


def _close_series(frame: pd.DataFrame) -> pd.Series:
    if "Close" in frame.columns:
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    if "close" in frame.columns:
        return pd.to_numeric(frame["close"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def _passes_overfit_guard(artifact: dict[str, Any]) -> bool:
    validation = artifact.get("validation")
    if not isinstance(validation, dict):
        return True
    guard = validation.get("overfit_guard")
    if not isinstance(guard, dict):
        return True
    return guard.get("passes") is not False


def _artifact_score(artifact: dict[str, Any]) -> float:
    validation_fitness = _validation_fitness(artifact)
    best_fitness = _coerce_float(artifact.get("best_fitness"))
    value = validation_fitness if validation_fitness is not None else best_fitness
    return value if value is not None else float("-inf")


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


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.notna(number):
        return number
    return None
