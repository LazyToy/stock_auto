from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, List, Tuple

import numpy as np
import pandas as pd

from src.optimization.strategy_registry import get_strategy_spec, normalize_strategy_type
from src.optimization.regime import RegimeConfig, apply_regime_filter, detect_regime_series
from src.optimization.risk import RiskConfig, simulate_long_only_with_risk
from src.optimization.resilient_reclaim import (
    build_resilient_reclaim_features,
    generate_reclaim_events,
)

logger = logging.getLogger("StrategyEvaluator")


_EXIT_REASON_KEYS = ["signal", "atr_stop", "trailing_stop", "max_holding"]


def _exit_reason_metrics(exit_reasons: dict[str, int]) -> dict[str, float]:
    return {
        f"{reason}_exit_count": float(exit_reasons.get(reason, 0))
        for reason in _EXIT_REASON_KEYS
    }


def _build_train_test_overfit_guard(
    result: dict[str, Any],
    *,
    min_trades: int,
    max_fitness_gap: float,
) -> dict[str, Any]:
    test = result.get("test", {})
    train = result.get("train", {})
    test_metrics = test.get("metrics", {}) if isinstance(test, dict) else {}
    train_metrics = train.get("metrics", {}) if isinstance(train, dict) else {}
    fitness_gap = _safe_float(result.get("fitness_gap"))
    test_trade_count = _safe_float(test_metrics.get("trade_count"))
    train_sharpe = _safe_float(train_metrics.get("sharpe"))
    test_sharpe = _safe_float(test_metrics.get("sharpe"))

    failed_checks: list[str] = []
    if test_trade_count < float(min_trades):
        failed_checks.append("min_trades")
    if abs(fitness_gap) > float(max_fitness_gap):
        failed_checks.append("fitness_gap")

    return {
        "passes": not failed_checks,
        "failed_checks": failed_checks,
        "min_trades": int(min_trades),
        "max_fitness_gap": float(max_fitness_gap),
        "deflated_sharpe": _deflated_sharpe_proxy(test_sharpe, train_sharpe),
    }


def _build_walk_forward_overfit_guard(
    result: dict[str, Any],
    *,
    min_trades: int,
    max_fold_std: float,
) -> dict[str, Any]:
    folds = result.get("folds", [])
    aggregate = result.get("aggregate", {})
    test_trade_counts = [
        _safe_float(fold.get("test", {}).get("metrics", {}).get("trade_count"))
        for fold in folds
        if isinstance(fold, dict)
    ]
    min_test_trades = min(test_trade_counts) if test_trade_counts else 0.0
    fold_std = _safe_float(aggregate.get("test_fitness_std")) if isinstance(aggregate, dict) else 0.0
    average_test_fitness = (
        _safe_float(aggregate.get("average_test_fitness")) if isinstance(aggregate, dict) else 0.0
    )

    failed_checks: list[str] = []
    if min_test_trades < float(min_trades):
        failed_checks.append("min_trades")
    if fold_std > float(max_fold_std):
        failed_checks.append("fold_dispersion")

    return {
        "passes": not failed_checks,
        "failed_checks": failed_checks,
        "min_trades": int(min_trades),
        "max_fold_std": float(max_fold_std),
        "min_test_trades": float(min_test_trades),
        "deflated_sharpe": _deflated_sharpe_proxy(average_test_fitness, fold_std),
    }


def _deflated_sharpe_proxy(test_sharpe: float, reference: float) -> float:
    penalty = max(abs(reference - test_sharpe), 0.0) * 0.25
    return float(test_sharpe - penalty)


def _stability_score(average: float, std: float) -> float:
    return float(average / (1.0 + max(std, 0.0)))


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if np.isfinite(number):
        return number
    return 0.0


@dataclass(frozen=True)
class EvaluationResult:
    """Detailed AutoML evaluation result."""

    strategy_type: str
    params: list[float]
    fitness: float
    metrics: dict[str, float]


class StrategyEvaluator:
    """
    유전자 알고리즘을 위한 전략 평가기.

    기존 DEAP 호환 `evaluate()`는 `(fitness,)` 튜플을 유지하고,
    대시보드/검증용 상세 지표는 `evaluate_detailed()`로 제공한다.
    """

    def __init__(
        self,
        initial_capital: float = 10000000,
        fee: float = 0.0015,
        slippage: float = 0.0,
        tax: float = 0.0,
        risk_config: RiskConfig | None = None,
        use_regime_filter: bool = False,
        regime_config: RegimeConfig | None = None,
    ):
        self.initial_capital = initial_capital
        self.fee = fee
        self.slippage = slippage
        self.tax = tax
        self.risk_config = risk_config or RiskConfig()
        self.use_regime_filter = bool(use_regime_filter)
        self.regime_config = regime_config or RegimeConfig()

    def evaluate(
        self,
        df: pd.DataFrame,
        params: List[float],
        strategy_type: str = "MACD_RSI",
        fitness_metric: str = "sharpe",
    ) -> Tuple[float]:
        """
        전략 파라미터 평가.

        Returns:
            (fitness, ) - DEAP requires tuple
        """
        if df is None or df.empty:
            return (-9999.0,)

        try:
            return (
                self.evaluate_detailed(
                    df,
                    params,
                    strategy_type=strategy_type,
                    fitness_metric=fitness_metric,
                ).fitness,
            )
        except Exception as e:
            logger.error("Evaluation failed: %s", e)
            return (-9999.0,)

    def evaluate_detailed(
        self,
        df: pd.DataFrame,
        params: List[float],
        strategy_type: str = "MACD_RSI",
        fitness_metric: str = "sharpe",
    ) -> EvaluationResult:
        """Return fitness plus risk/turnover metrics for one full sample."""
        normalized_type = normalize_strategy_type(strategy_type)
        if df is None or df.empty:
            return self._penalty_result(normalized_type, params, -9999.0)

        close = self._extract_close(df)
        if close.empty:
            return self._penalty_result(normalized_type, params, -9999.0)

        if not self._validate_params(normalized_type, params):
            return self._penalty_result(normalized_type, params, -999.0)

        signal_events = self.build_signal_events(df, params, normalized_type)
        regime_blocked_buy_count = 0
        if self.use_regime_filter:
            regimes = detect_regime_series(df, self.regime_config)
            if normalized_type == "ENSEMBLE_VOTE":
                filtered_events = self._ensemble_vote_events(close, params, regimes=regimes)
            else:
                filtered_events = apply_regime_filter(signal_events, regimes, normalized_type)
            regime_blocked_buy_count = int(((signal_events > 0) & (filtered_events <= 0)).sum())
            signal_events = filtered_events
        simulation = self._simulate_long_only(df, signal_events)
        metrics = self._calculate_metrics(
            close,
            simulation.returns,
            simulation.trade_count,
            simulation.exit_reasons,
        )
        metrics["regime_blocked_buy_count"] = float(regime_blocked_buy_count)
        fitness = self._select_fitness(metrics, fitness_metric)

        return EvaluationResult(
            strategy_type=normalized_type,
            params=[float(value) for value in params],
            fitness=float(fitness),
            metrics=metrics,
        )

    def build_signal_events(
        self,
        df: pd.DataFrame,
        params: List[float],
        strategy_type: str = "MACD_RSI",
    ) -> pd.Series:
        """Build raw signal events for monitors and strategy research tools."""
        normalized_type = normalize_strategy_type(strategy_type)
        if df is None or df.empty:
            return pd.Series(dtype=int)
        close = self._extract_close(df)
        if close.empty:
            return pd.Series(dtype=int)
        if not self._validate_params(normalized_type, params):
            raise ValueError(f"Invalid parameters for {normalized_type}")
        if normalized_type == "RESILIENT_RECLAIM":
            return self._resilient_reclaim_events(df, params)
        return self._generate_signal_events(close, params, normalized_type)

    def evaluate_validation(
        self,
        df: pd.DataFrame,
        params: List[float],
        strategy_type: str = "MACD_RSI",
        validation_method: str = "train_test",
        train_ratio: float = 0.7,
        train_window: int = 126,
        test_window: int = 21,
        fitness_metric: str = "composite",
        min_trades: int = 1,
        max_fitness_gap: float = 2.0,
        max_fold_std: float = 3.0,
    ) -> dict[str, Any]:
        """Evaluate parameters with train/test or walk-forward validation."""
        if df is None or df.empty:
            return {"method": validation_method, "error": "empty dataframe"}

        method = validation_method.strip().lower()
        if method in {"none", ""}:
            return {"method": "none"}
        if method == "train_test":
            return self._evaluate_train_test(
                df,
                params,
                strategy_type=strategy_type,
                train_ratio=train_ratio,
                fitness_metric=fitness_metric,
                min_trades=min_trades,
                max_fitness_gap=max_fitness_gap,
            )
        if method == "walk_forward":
            return self._evaluate_walk_forward(
                df,
                params,
                strategy_type=strategy_type,
                train_window=train_window,
                test_window=test_window,
                fitness_metric=fitness_metric,
                min_trades=min_trades,
                max_fold_std=max_fold_std,
            )

        raise ValueError(f"지원하지 않는 validation_method입니다: {validation_method}")

    def evaluate_event_strategy(
        self,
        df: pd.DataFrame,
        event_builder: Callable[[pd.DataFrame], pd.Series],
        *,
        strategy_type: str = "EVENT_STRATEGY",
        fitness_metric: str = "composite",
        risk_config: RiskConfig | None = None,
    ) -> EvaluationResult:
        """Evaluate a strategy whose events are built from this dataframe slice."""
        if df is None or df.empty:
            return self._penalty_result(strategy_type, [], -9999.0)

        close = self._extract_close(df)
        if close.empty:
            return self._penalty_result(strategy_type, [], -9999.0)

        try:
            signal_events = event_builder(df)
            if not isinstance(signal_events, pd.Series):
                signal_events = pd.Series(signal_events, index=df.index)
            simulation = simulate_long_only_with_risk(
                df,
                signal_events,
                risk_config or self.risk_config,
                fee=self.fee,
                slippage=self.slippage,
                tax=self.tax,
            )
            metrics = self._calculate_metrics(
                close,
                simulation.returns,
                simulation.trade_count,
                simulation.exit_reasons,
            )
            fitness = self._select_fitness(metrics, fitness_metric)
        except Exception as exc:
            logger.error("Event strategy evaluation failed: %s", exc)
            return self._penalty_result(strategy_type, [], -9999.0)

        return EvaluationResult(
            strategy_type=str(strategy_type),
            params=[],
            fitness=float(fitness),
            metrics=metrics,
        )

    def evaluate_event_strategy_validation(
        self,
        df: pd.DataFrame,
        event_builder: Callable[[pd.DataFrame], pd.Series],
        *,
        strategy_type: str = "EVENT_STRATEGY",
        validation_method: str = "train_test",
        train_ratio: float = 0.7,
        train_window: int = 126,
        test_window: int = 21,
        fitness_metric: str = "composite",
        min_trades: int = 1,
        max_fitness_gap: float = 2.0,
        max_fold_std: float = 3.0,
        risk_config: RiskConfig | None = None,
    ) -> dict[str, Any]:
        """Validate an event builder without registering it as a GA strategy."""
        if df is None or df.empty:
            return {"method": validation_method, "error": "empty dataframe"}

        method = validation_method.strip().lower()
        if method in {"none", ""}:
            return {"method": "none"}
        if method == "train_test":
            return self._evaluate_event_strategy_train_test(
                df,
                event_builder,
                strategy_type=strategy_type,
                train_ratio=train_ratio,
                fitness_metric=fitness_metric,
                min_trades=min_trades,
                max_fitness_gap=max_fitness_gap,
                risk_config=risk_config,
            )
        if method == "walk_forward":
            return self._evaluate_event_strategy_walk_forward(
                df,
                event_builder,
                strategy_type=strategy_type,
                train_window=train_window,
                test_window=test_window,
                fitness_metric=fitness_metric,
                min_trades=min_trades,
                max_fold_std=max_fold_std,
                risk_config=risk_config,
            )

        raise ValueError(f"Unsupported validation_method: {validation_method}")

    def _evaluate_train_test(
        self,
        df: pd.DataFrame,
        params: List[float],
        *,
        strategy_type: str,
        train_ratio: float,
        fitness_metric: str,
        min_trades: int,
        max_fitness_gap: float,
    ) -> dict[str, Any]:
        split_idx = int(len(df) * train_ratio)
        split_idx = max(1, min(split_idx, len(df) - 1))
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]

        train = self.evaluate_detailed(
            train_df,
            params,
            strategy_type=strategy_type,
            fitness_metric=fitness_metric,
        )
        test = self.evaluate_detailed(
            test_df,
            params,
            strategy_type=strategy_type,
            fitness_metric=fitness_metric,
        )

        result = {
            "method": "train_test",
            "train_size": int(len(train_df)),
            "test_size": int(len(test_df)),
            "train": self._serialize_result(train),
            "test": self._serialize_result(test),
            "fitness_gap": float(train.fitness - test.fitness),
        }
        result["overfit_guard"] = _build_train_test_overfit_guard(
            result,
            min_trades=min_trades,
            max_fitness_gap=max_fitness_gap,
        )
        return result

    def _evaluate_event_strategy_train_test(
        self,
        df: pd.DataFrame,
        event_builder: Callable[[pd.DataFrame], pd.Series],
        *,
        strategy_type: str,
        train_ratio: float,
        fitness_metric: str,
        min_trades: int,
        max_fitness_gap: float,
        risk_config: RiskConfig | None,
    ) -> dict[str, Any]:
        split_idx = int(len(df) * train_ratio)
        split_idx = max(1, min(split_idx, len(df) - 1))
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]

        train = self.evaluate_event_strategy(
            train_df,
            event_builder,
            strategy_type=strategy_type,
            fitness_metric=fitness_metric,
            risk_config=risk_config,
        )
        test = self.evaluate_event_strategy(
            test_df,
            event_builder,
            strategy_type=strategy_type,
            fitness_metric=fitness_metric,
            risk_config=risk_config,
        )

        result = {
            "method": "train_test",
            "train_size": int(len(train_df)),
            "test_size": int(len(test_df)),
            "train": self._serialize_result(train),
            "test": self._serialize_result(test),
            "fitness_gap": float(train.fitness - test.fitness),
        }
        result["overfit_guard"] = _build_train_test_overfit_guard(
            result,
            min_trades=min_trades,
            max_fitness_gap=max_fitness_gap,
        )
        return result

    def _evaluate_event_strategy_walk_forward(
        self,
        df: pd.DataFrame,
        event_builder: Callable[[pd.DataFrame], pd.Series],
        *,
        strategy_type: str,
        train_window: int,
        test_window: int,
        fitness_metric: str,
        min_trades: int,
        max_fold_std: float,
        risk_config: RiskConfig | None,
    ) -> dict[str, Any]:
        if train_window <= 0 or test_window <= 0:
            raise ValueError("train_window and test_window must be positive")

        folds: list[dict[str, Any]] = []
        step = test_window
        start = 0
        while start + train_window + test_window <= len(df):
            train_df = df.iloc[start : start + train_window]
            test_df = df.iloc[start + train_window : start + train_window + test_window]
            train = self.evaluate_event_strategy(
                train_df,
                event_builder,
                strategy_type=strategy_type,
                fitness_metric=fitness_metric,
                risk_config=risk_config,
            )
            test = self.evaluate_event_strategy(
                test_df,
                event_builder,
                strategy_type=strategy_type,
                fitness_metric=fitness_metric,
                risk_config=risk_config,
            )
            folds.append(
                {
                    "fold": len(folds) + 1,
                    "train": self._serialize_result(train),
                    "test": self._serialize_result(test),
                }
            )
            start += step

        test_fitness = [fold["test"]["fitness"] for fold in folds]
        test_fitness_std = float(np.std(test_fitness)) if test_fitness else 0.0
        average_test_fitness = float(np.mean(test_fitness)) if test_fitness else 0.0
        aggregate = {
            "average_test_fitness": average_test_fitness,
            "min_test_fitness": float(np.min(test_fitness)) if test_fitness else 0.0,
            "max_test_fitness": float(np.max(test_fitness)) if test_fitness else 0.0,
            "test_fitness_std": test_fitness_std,
            "stability_score": _stability_score(average_test_fitness, test_fitness_std),
        }

        result = {
            "method": "walk_forward",
            "train_window": int(train_window),
            "test_window": int(test_window),
            "fold_count": len(folds),
            "folds": folds,
            "aggregate": aggregate,
        }
        result["overfit_guard"] = _build_walk_forward_overfit_guard(
            result,
            min_trades=min_trades,
            max_fold_std=max_fold_std,
        )
        return result

    def _evaluate_walk_forward(
        self,
        df: pd.DataFrame,
        params: List[float],
        *,
        strategy_type: str,
        train_window: int,
        test_window: int,
        fitness_metric: str,
        min_trades: int,
        max_fold_std: float,
    ) -> dict[str, Any]:
        if train_window <= 0 or test_window <= 0:
            raise ValueError("train_window와 test_window는 1 이상이어야 합니다.")

        folds: list[dict[str, Any]] = []
        step = test_window
        start = 0
        while start + train_window + test_window <= len(df):
            train_df = df.iloc[start : start + train_window]
            test_df = df.iloc[start + train_window : start + train_window + test_window]
            train = self.evaluate_detailed(
                train_df,
                params,
                strategy_type=strategy_type,
                fitness_metric=fitness_metric,
            )
            test = self.evaluate_detailed(
                test_df,
                params,
                strategy_type=strategy_type,
                fitness_metric=fitness_metric,
            )
            folds.append(
                {
                    "fold": len(folds) + 1,
                    "train": self._serialize_result(train),
                    "test": self._serialize_result(test),
                }
            )
            start += step

        test_fitness = [fold["test"]["fitness"] for fold in folds]
        test_fitness_std = float(np.std(test_fitness)) if test_fitness else 0.0
        average_test_fitness = float(np.mean(test_fitness)) if test_fitness else 0.0
        aggregate = {
            "average_test_fitness": average_test_fitness,
            "min_test_fitness": float(np.min(test_fitness)) if test_fitness else 0.0,
            "max_test_fitness": float(np.max(test_fitness)) if test_fitness else 0.0,
            "test_fitness_std": test_fitness_std,
            "stability_score": _stability_score(average_test_fitness, test_fitness_std),
        }

        result = {
            "method": "walk_forward",
            "train_window": int(train_window),
            "test_window": int(test_window),
            "fold_count": len(folds),
            "folds": folds,
            "aggregate": aggregate,
        }
        result["overfit_guard"] = _build_walk_forward_overfit_guard(
            result,
            min_trades=min_trades,
            max_fold_std=max_fold_std,
        )
        return result

    def _extract_close(self, df: pd.DataFrame) -> pd.Series:
        if "Close" in df.columns:
            close = df["Close"]
        elif "close" in df.columns:
            close = df["close"]
        else:
            return pd.Series(dtype=float)

        return pd.to_numeric(close, errors="coerce").dropna()

    def _validate_params(self, strategy_type: str, params: List[float]) -> bool:
        spec = get_strategy_spec(strategy_type)
        if not spec.validate_param_count(params):
            return False

        values = [float(value) for value in params]
        if strategy_type == "MACD_RSI":
            return (
                values[0] < values[1]
                and values[0] >= 2
                and values[1] >= 5
                and values[4] < values[5]
                and values[3] >= 2
            )
        if strategy_type == "MACD":
            return values[0] < values[1] and values[0] >= 2 and values[1] >= 5
        if strategy_type == "MA_CROSSOVER":
            return values[0] < values[1] and values[0] >= 1
        if strategy_type == "RSI":
            return values[1] < values[2] and values[0] >= 2
        if strategy_type == "BOLLINGER":
            return values[0] >= 2 and values[1] > 0 and values[2] >= 0
        if strategy_type == "ENSEMBLE_VOTE":
            return (
                values[0].is_integer()
                and values[1].is_integer()
                and 1 <= values[0] <= 2
                and 1 <= values[1] <= 2
            )
        if strategy_type == "RESILIENT_RECLAIM":
            return (
                values[0] >= 2
                and values[1] >= 1
                and values[2] >= 1
                and values[0] >= values[2]
                and values[3] > 0
                and 0 <= values[4]
                and 0 < values[5] < 10000
            )
        return False

    def _generate_signal_events(
        self,
        close: pd.Series,
        params: List[float],
        strategy_type: str,
    ) -> pd.Series:
        if strategy_type == "MACD_RSI":
            return self._macd_rsi_events(close, params)
        if strategy_type == "MA_CROSSOVER":
            return self._ma_crossover_events(close, params)
        if strategy_type == "RSI":
            return self._rsi_events(close, params)
        if strategy_type == "MACD":
            return self._macd_events(close, params)
        if strategy_type == "BOLLINGER":
            return self._bollinger_events(close, params)
        if strategy_type == "ENSEMBLE_VOTE":
            return self._ensemble_vote_events(close, params)

        raise ValueError(f"지원하지 않는 AutoML 전략입니다: {strategy_type}")

    def _macd_rsi_events(self, close: pd.Series, params: List[float]) -> pd.Series:
        n_fast = int(params[0])
        n_slow = int(params[1])
        n_signal = int(params[2])
        n_rsi = int(params[3])
        rsi_lower = float(params[4])
        rsi_upper = float(params[5])

        macd, signal = self._calculate_macd(close, n_fast, n_slow, n_signal)
        rsi = self._calculate_rsi(close, n_rsi)
        buy = (macd > signal) & (rsi < rsi_lower)
        sell = (macd < signal) | (rsi > rsi_upper)
        return self._events_from_conditions(close.index, buy, sell)

    def _ma_crossover_events(self, close: pd.Series, params: List[float]) -> pd.Series:
        short_window, long_window = [int(value) for value in params]
        short_ma = close.rolling(short_window, min_periods=1).mean()
        long_ma = close.rolling(long_window, min_periods=1).mean()
        buy = (short_ma.shift(1) <= long_ma.shift(1)) & (short_ma > long_ma)
        sell = (short_ma.shift(1) >= long_ma.shift(1)) & (short_ma < long_ma)
        return self._events_from_conditions(close.index, buy, sell)

    def _rsi_events(self, close: pd.Series, params: List[float]) -> pd.Series:
        window, lower, upper = int(params[0]), float(params[1]), float(params[2])
        rsi = self._calculate_rsi(close, window)
        buy = (rsi <= lower) | ((rsi.shift(1) <= lower) & (rsi > lower))
        sell = (rsi >= upper) | ((rsi.shift(1) >= upper) & (rsi < upper))
        return self._events_from_conditions(close.index, buy, sell)

    def _macd_events(self, close: pd.Series, params: List[float]) -> pd.Series:
        fast, slow, signal_span = [int(value) for value in params]
        macd, signal = self._calculate_macd(close, fast, slow, signal_span)
        buy = (macd.shift(1) <= signal.shift(1)) & (macd > signal)
        sell = (macd.shift(1) >= signal.shift(1)) & (macd < signal)
        return self._events_from_conditions(close.index, buy, sell)

    def _bollinger_events(self, close: pd.Series, params: List[float]) -> pd.Series:
        period = int(params[0])
        std_dev = float(params[1]) / 10.0
        proximity = float(params[2]) / 10000.0
        middle = close.rolling(period, min_periods=1).mean()
        rolling_std = close.rolling(period, min_periods=1).std().fillna(0.0)
        upper = middle + (rolling_std * std_dev)
        lower = middle - (rolling_std * std_dev)
        buy = close <= lower * (1 + proximity)
        sell = (close >= middle) | (close >= upper * (1 - proximity))
        return self._events_from_conditions(close.index, buy, sell)

    def _ensemble_vote_events(
        self,
        close: pd.Series,
        params: List[float],
        regimes: pd.Series | None = None,
    ) -> pd.Series:
        trend_threshold = int(params[0])
        mean_reversion_threshold = int(params[1])
        trend_events = [
            self._ma_crossover_events(close, [10, 40]),
            self._macd_events(close, [12, 26, 9]),
        ]
        mean_reversion_events = [
            self._rsi_events(close, [14, 30, 70]),
            self._bollinger_events(close, [20, 20, 100]),
        ]
        if regimes is not None:
            trend_events = [
                apply_regime_filter(trend_events[0], regimes, "MA_CROSSOVER"),
                apply_regime_filter(trend_events[1], regimes, "MACD"),
            ]
            mean_reversion_events = [
                apply_regime_filter(mean_reversion_events[0], regimes, "RSI"),
                apply_regime_filter(mean_reversion_events[1], regimes, "BOLLINGER"),
            ]

        trend_buy_votes = sum((events > 0).astype(int) for events in trend_events)
        trend_sell_votes = sum((events < 0).astype(int) for events in trend_events)
        mean_reversion_buy_votes = sum(
            (events > 0).astype(int) for events in mean_reversion_events
        )
        mean_reversion_sell_votes = sum(
            (events < 0).astype(int) for events in mean_reversion_events
        )

        buy = (trend_buy_votes >= trend_threshold) | (
            mean_reversion_buy_votes >= mean_reversion_threshold
        )
        sell = (trend_sell_votes >= trend_threshold) | (
            mean_reversion_sell_votes >= mean_reversion_threshold
        )
        return self._events_from_conditions(close.index, buy, sell)

    def _resilient_reclaim_events(self, df: pd.DataFrame, params: List[float]) -> pd.Series:
        high_window = int(params[0])
        momentum_window = int(params[1])
        reclaim_lookback = int(params[2])
        proximity_threshold = float(params[3]) / 10000.0
        min_residual_momentum = float(params[4]) / 10000.0
        failure_buffer = float(params[5]) / 10000.0
        features = build_resilient_reclaim_features(
            df,
            high_window=high_window,
            momentum_window=momentum_window,
        )
        return generate_reclaim_events(
            features,
            proximity_threshold=proximity_threshold,
            reclaim_lookback=reclaim_lookback,
            min_residual_momentum=min_residual_momentum,
            failure_buffer=failure_buffer,
        )

    def _calculate_macd(
        self,
        close: pd.Series,
        fast: int,
        slow: int,
        signal_span: int,
    ) -> tuple[pd.Series, pd.Series]:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signal_span, adjust=False).mean()
        return macd, signal

    def _calculate_rsi(self, close: pd.Series, window: int) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=window).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
        rsi = rsi.mask((loss == 0) & (gain == 0), 50.0)
        return rsi

    def _events_from_conditions(
        self,
        index: pd.Index,
        buy: pd.Series,
        sell: pd.Series,
    ) -> pd.Series:
        events = pd.Series(0, index=index, dtype=int)
        events.loc[buy.fillna(False)] = 1
        events.loc[sell.fillna(False)] = -1
        return events

    def _simulate_long_only(
        self,
        df: pd.DataFrame,
        events: pd.Series,
    ):
        return simulate_long_only_with_risk(
            df,
            events,
            self.risk_config,
            fee=self.fee,
            slippage=self.slippage,
            tax=self.tax,
        )

    def _calculate_metrics(
        self,
        close: pd.Series,
        strategy_returns: np.ndarray,
        trade_count: int,
        exit_reasons: dict[str, int] | None = None,
    ) -> dict[str, float]:
        if len(strategy_returns) == 0:
            return self._empty_metrics()

        mean_ret = float(np.mean(strategy_returns))
        std_ret = float(np.std(strategy_returns))
        sharpe = 0.0 if std_ret == 0 else float((mean_ret / std_ret) * np.sqrt(252))
        equity = np.cumprod(1 + strategy_returns)
        peak = np.maximum.accumulate(equity)
        drawdown = np.divide(equity, peak, out=np.ones_like(equity), where=peak != 0) - 1
        max_drawdown = float(np.min(drawdown)) if len(drawdown) else 0.0
        total_return = float(equity[-1] - 1) if len(equity) else 0.0
        benchmark_return = float(close.iloc[-1] / close.iloc[0] - 1) if len(close) > 1 else 0.0
        positive = strategy_returns[strategy_returns > 0].sum()
        negative = strategy_returns[strategy_returns < 0].sum()
        profit_factor = float(positive / abs(negative)) if negative < 0 else 0.0
        turnover = float(trade_count / max(len(strategy_returns), 1))
        annual_return = (
            float((1 + total_return) ** (252 / max(len(strategy_returns), 1)) - 1)
            if total_return > -1
            else -1.0
        )

        metrics = {
            "sharpe": sharpe,
            "total_return": total_return,
            "annual_return": annual_return,
            "benchmark_return": benchmark_return,
            "excess_return": total_return - benchmark_return,
            "max_drawdown": max_drawdown,
            "profit_factor": profit_factor,
            "trade_count": float(trade_count),
            "turnover": turnover,
        }
        metrics.update(_exit_reason_metrics(exit_reasons or {}))
        return metrics

    def _empty_metrics(self) -> dict[str, float]:
        return {
            "sharpe": 0.0,
            "total_return": 0.0,
            "annual_return": 0.0,
            "benchmark_return": 0.0,
            "excess_return": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "trade_count": 0.0,
            "turnover": 0.0,
            "regime_blocked_buy_count": 0.0,
            **_exit_reason_metrics({}),
        }

    def _select_fitness(self, metrics: dict[str, float], fitness_metric: str) -> float:
        metric = fitness_metric.strip().lower()
        if metric == "sharpe":
            return metrics["sharpe"]
        if metric == "composite":
            return (
                metrics["sharpe"]
                + metrics["excess_return"]
                - abs(metrics["max_drawdown"]) * 2.0
                - metrics["turnover"] * 0.1
            )
        if metric in metrics:
            return metrics[metric]
        raise ValueError(f"지원하지 않는 fitness_metric입니다: {fitness_metric}")

    def _penalty_result(
        self,
        strategy_type: str,
        params: List[float],
        fitness: float,
    ) -> EvaluationResult:
        metrics = self._empty_metrics()
        metrics["sharpe"] = float(fitness)
        return EvaluationResult(
            strategy_type=strategy_type,
            params=[float(value) for value in params],
            fitness=float(fitness),
            metrics=metrics,
        )

    def _serialize_result(self, result: EvaluationResult) -> dict[str, Any]:
        return {
            "strategy_type": result.strategy_type,
            "params": result.params,
            "fitness": float(result.fitness),
            "metrics": {key: float(value) for key, value in result.metrics.items()},
        }
