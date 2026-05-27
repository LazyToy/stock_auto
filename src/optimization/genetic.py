import math
import random
import numpy as np
import pandas as pd
from dataclasses import asdict
from typing import Any, List, Optional, Tuple
from deap import base, creator, tools, algorithms
from src.optimization.evaluator import StrategyEvaluator
from src.optimization.regime import RegimeConfig
from src.optimization.risk import RiskConfig
from src.optimization.automl_support import extract_fitness_history
from src.optimization.strategy_registry import get_strategy_spec, normalize_strategy_type
import logging

logger = logging.getLogger("GeneticOptimizer")

# DEAP needs global creator setup (doing this only once)
# Create FitnessMax and Individual classes
if not hasattr(creator, "FitnessMax"):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))

if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMax)

class GeneticOptimizer:
    """
    유전자 알고리즘 최적화기
    """
    
    def __init__(
        self,
        df: Optional[pd.DataFrame] = None,
        population_size=50,
        generations=10,
        mutation_rate=0.2,
        strategy_type: str = "MACD_RSI",
        fitness_metric: str = "sharpe",
        use_regime_filter: bool = True,
        regime_config: RegimeConfig | None = None,
        risk_config: RiskConfig | None = None,
    ):
        self.df = df
        self.pop_size = population_size
        self.ngen = generations
        self.mutation_rate = mutation_rate
        self.strategy_type = normalize_strategy_type(strategy_type)
        self.fitness_metric = fitness_metric
        self.use_regime_filter = bool(use_regime_filter)
        self.regime_config = regime_config
        self.risk_config = risk_config
        self.evaluator = StrategyEvaluator(
            risk_config=risk_config,
            use_regime_filter=use_regime_filter,
            regime_config=regime_config,
        )
        self.toolbox = base.Toolbox()
        self._configure_toolbox()

    def _configure_toolbox(self) -> None:
        """현재 strategy spec에 맞게 DEAP toolbox를 구성한다."""
        spec = get_strategy_spec(self.strategy_type)
        self.toolbox = base.Toolbox()

        attr_generators = []
        for idx, (low, up) in enumerate(zip(spec.low_bounds, spec.up_bounds)):
            attr_name = f"attr_param_{idx}"
            self.toolbox.register(attr_name, random.randint, low, up)
            attr_generators.append(getattr(self.toolbox, attr_name))

        self.toolbox.register(
            "individual",
            tools.initCycle,
            creator.Individual,
            tuple(attr_generators),
            n=1,
        )
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("evaluate", self._evaluate_wrapper)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register(
            "mutate",
            tools.mutUniformInt,
            low=spec.low_bounds,
            up=spec.up_bounds,
            indpb=self.mutation_rate,
        )
        self.toolbox.register("select", tools.selTournament, tournsize=3)

    def _evaluate_wrapper(self, individual):
        """DEAP evaluate wrapper"""
        if self.fitness_metric == "sharpe":
            return self.evaluator.evaluate(
                self.df,
                individual,
                strategy_type=self.strategy_type,
            )
        return self.evaluator.evaluate(
            self.df,
            individual,
            strategy_type=self.strategy_type,
            fitness_metric=self.fitness_metric,
        )

    def set_strategy_type(self, strategy_type: str) -> None:
        """전략이 바뀌면 parameter space도 함께 재구성한다."""
        normalized = normalize_strategy_type(strategy_type)
        if normalized != self.strategy_type:
            self.strategy_type = normalized
            self._configure_toolbox()

    def run(self) -> Tuple[List[float], float, object]:
        """최적화 실행. (best_params, best_fitness, logbook) 튜플을 반환"""
        if self.df is None or self.df.empty:
            logger.error("최적화에 필요한 DataFrame이 없거나 비어 있습니다.")
            return [], 0.0, None

        try:
            pop = self.toolbox.population(n=self.pop_size)
            hof = tools.HallOfFame(1)

            # 세대별 통계 (avg, min, max fitness)
            stats = tools.Statistics(lambda ind: ind.fitness.values[0])
            stats.register("avg", np.mean)
            stats.register("min", np.min)
            stats.register("max", np.max)

            # 진화 알고리즘 실행
            log = tools.Logbook()
            log.header = ["gen", "nevals", *stats.fields, "best_params", "best_fitness"]

            invalid_ind = [ind for ind in pop if not ind.fitness.valid]
            fitnesses = map(self.toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit

            hof.update(pop)
            self._record_generation(log, pop, stats, gen=0, nevals=len(invalid_ind))

            for gen in range(1, self.ngen + 1):
                offspring = self.toolbox.select(pop, len(pop))
                offspring = algorithms.varAnd(
                    offspring,
                    self.toolbox,
                    cxpb=0.5,
                    mutpb=self.mutation_rate,
                )

                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
                fitnesses = map(self.toolbox.evaluate, invalid_ind)
                for ind, fit in zip(invalid_ind, fitnesses):
                    ind.fitness.values = fit

                hof.update(offspring)
                pop[:] = offspring
                self._record_generation(log, pop, stats, gen=gen, nevals=len(invalid_ind))

            best_ind = hof[0]
            logger.info(f"최적 개체: {best_ind}, Fitness: {best_ind.fitness.values[0]}")

            return list(best_ind), best_ind.fitness.values[0], log

        except Exception as e:
            logger.error(f"최적화 실패: {e}")
            return [], 0.0, None

    def _record_generation(self, log, pop, stats, *, gen: int, nevals: int) -> None:
        record = stats.compile(pop)
        best_ind = tools.selBest(pop, 1)[0]
        best_fitness = float(best_ind.fitness.values[0])
        log.record(
            gen=gen,
            nevals=nevals,
            **record,
            best_params=list(best_ind),
            best_fitness=best_fitness,
        )

    def evolve(
        self,
        symbol: str | None = None,
        df: Optional[pd.DataFrame] = None,
        strategy_type: str | None = None,
        fitness_metric: str | None = None,
        validation_method: str | None = None,
        validation_kwargs: Optional[dict] = None,
        progress_callback=None,
    ) -> dict:
        """대시보드 친화적인 run() 래퍼. history 포함 결과 dict 반환."""
        if df is not None:
            self.df = df
        if strategy_type is not None:
            self.set_strategy_type(strategy_type)
        if fitness_metric is not None:
            self.fitness_metric = fitness_metric

        if self.df is None or self.df.empty:
            raise ValueError(
                "GeneticOptimizer에는 가격 DataFrame이 필요합니다. "
                "evolve() 호출 전 df=... 를 전달하거나 초기화 시 df를 설정하세요."
            )

        if callable(progress_callback):
            progress_callback(0, max(self.ngen, 1))

        # run()은 이제 (best_params, best_fitness, logbook) 튜플 반환
        run_result = self.run()
        if len(run_result) == 3:
            best_params, best_fitness, logbook = run_result
        elif len(run_result) == 2:
            best_params, best_fitness = run_result
            logbook = None
        else:
            raise ValueError("run() 반환값 형식이 올바르지 않습니다.")

        if callable(progress_callback):
            progress_callback(max(self.ngen - 1, 0), max(self.ngen, 1))

        # 세대별 최고 fitness 기록 추출
        history = extract_fitness_history(
            logbook,
            fallback_fitness=best_fitness if best_params else None,
        )
        spec = get_strategy_spec(self.strategy_type)
        best_parameters = {
            label: value
            for label, value in zip(spec.parameter_labels, best_params)
        }

        validation = None
        if validation_method and best_params:
            validation_cache: dict[tuple[float, ...], dict[str, Any]] = {}
            validation = self._evaluate_validation_cached(
                best_params,
                validation_method=validation_method,
                validation_kwargs=validation_kwargs or {},
                cache=validation_cache,
            )
            generation_validation_history = self._build_generation_validation_history(
                logbook,
                history,
                validation_method=validation_method,
                validation_kwargs=validation_kwargs or {},
                cache=validation_cache,
            )
            if generation_validation_history:
                validation = dict(validation)
                validation["generation_history"] = generation_validation_history

        result = {
            "symbol": symbol,
            "strategy_type": self.strategy_type,
            "strategy_display_name": spec.display_name,
            "best_params": best_params,
            "best_parameters": best_parameters,
            "parameter_labels": list(spec.parameter_labels),
            "best_fitness": float(best_fitness),
            "fitness_metric": self.fitness_metric,
            "population_size": self.pop_size,
            "generations": self.ngen,
            "mutation_rate": self.mutation_rate,
            "history": history,
            "use_regime_filter": self.evaluator.use_regime_filter,
            "regime_config": asdict(self.evaluator.regime_config),
            "risk_config": asdict(self.evaluator.risk_config),
        }
        if validation is not None:
            result["validation"] = validation
        return result


    def _build_generation_validation_history(
        self,
        logbook: Any,
        history: list[float],
        *,
        validation_method: str,
        validation_kwargs: dict,
        cache: dict[tuple[float, ...], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for record in _extract_generation_best_records(logbook, history):
            params = record.get("params")
            if not params:
                continue
            validation = self._evaluate_validation_cached(
                params,
                validation_method=validation_method,
                validation_kwargs=validation_kwargs,
                cache=cache,
            )
            row: dict[str, Any] = {
                "generation": record["generation"],
                "fitness": record["fitness"],
                "params": list(params),
            }
            row.update(_summarize_generation_validation(validation))
            rows.append(row)

        return rows

    def _evaluate_validation_cached(
        self,
        params: list[float],
        *,
        validation_method: str,
        validation_kwargs: dict,
        cache: dict[tuple[float, ...], dict[str, Any]],
    ) -> dict[str, Any]:
        key = tuple(float(value) for value in params)
        if key not in cache:
            cache[key] = self.evaluator.evaluate_validation(
                self.df,
                params,
                strategy_type=self.strategy_type,
                fitness_metric=self.fitness_metric,
                validation_method=validation_method,
                **validation_kwargs,
            )
        return cache[key]


def _extract_generation_best_records(logbook: Any, history: list[float]) -> list[dict[str, Any]]:
    if not logbook:
        return []

    try:
        raw_records = list(logbook)
    except TypeError:
        return []

    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        if not hasattr(record, "get"):
            continue

        params = record.get("best_params")
        if params is None:
            continue

        fitness = _coerce_float(record.get("best_fitness"))
        if fitness is None:
            fitness = _coerce_float(record.get("max"))
        if fitness is None and index < len(history):
            fitness = _coerce_float(history[index])
        if fitness is None:
            continue

        generation = _coerce_int(record.get("gen"), fallback=index)
        records.append(
            {
                "generation": generation,
                "fitness": fitness,
                "params": list(params),
            }
        )

    return records


def _summarize_generation_validation(validation: dict[str, Any]) -> dict[str, float]:
    method = str(validation.get("method", "")).lower() if isinstance(validation, dict) else ""
    if method == "train_test":
        return _summarize_train_test_validation(validation)
    if method == "walk_forward":
        return _summarize_walk_forward_validation(validation)
    return {}


def _summarize_train_test_validation(validation: dict[str, Any]) -> dict[str, float]:
    summary: dict[str, float] = {}
    train = validation.get("train")
    test = validation.get("test")
    if isinstance(train, dict):
        train_fitness = _coerce_float(train.get("fitness"))
        if train_fitness is not None:
            summary["train_fitness"] = train_fitness
    if isinstance(test, dict):
        test_fitness = _coerce_float(test.get("fitness"))
        if test_fitness is not None:
            summary["test_fitness"] = test_fitness
    return summary


def _summarize_walk_forward_validation(validation: dict[str, Any]) -> dict[str, float]:
    summary: dict[str, float] = {}
    aggregate = validation.get("aggregate")
    if isinstance(aggregate, dict):
        for source_key, target_key in [
            ("average_test_fitness", "average_test_fitness"),
            ("min_test_fitness", "min_test_fitness"),
            ("max_test_fitness", "max_test_fitness"),
        ]:
            value = _coerce_float(aggregate.get(source_key))
            if value is not None:
                summary[target_key] = value
    return summary


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None


def _coerce_int(value: Any, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


if __name__ == "__main__":
    # Test
    np.random.seed(42)  # 재현 가능한 랜덤 데이터 생성
    # Create dummy data
    dates = pd.date_range(start='2023-01-01', periods=200, freq='D')
    df = pd.DataFrame({
        'Close': np.cumsum(np.random.normal(0, 1, 200)) + 100
    }, index=dates)
    
    optimizer = GeneticOptimizer(df, population_size=20, generations=5)
    best_params, fitness, _ = optimizer.run()
    print(f"결과: {best_params} (Sharpe: {fitness:.4f})")
