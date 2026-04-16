import random
import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
from deap import base, creator, tools, algorithms
from src.optimization.evaluator import StrategyEvaluator
from src.optimization.automl_support import extract_fitness_history
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
    Target Strategy: MACD_RSI
    """
    
    def __init__(
        self,
        df: Optional[pd.DataFrame] = None,
        population_size=50,
        generations=10,
        mutation_rate=0.2,
    ):
        self.df = df
        self.pop_size = population_size
        self.ngen = generations
        self.mutation_rate = mutation_rate
        self.evaluator = StrategyEvaluator()
        
        self.toolbox = base.Toolbox()
        
        # Attribute generators
        # Params: [fast, slow, signal, rsi_window, rsi_lower, rsi_upper]
        self.toolbox.register("attr_fast", random.randint, 5, 20)
        self.toolbox.register("attr_slow", random.randint, 21, 60)
        self.toolbox.register("attr_signal", random.randint, 5, 15)
        self.toolbox.register("attr_rsi_win", random.randint, 10, 30)
        self.toolbox.register("attr_rsi_low", random.randint, 20, 40)
        self.toolbox.register("attr_rsi_high", random.randint, 60, 80)
        
        # Structure initializers
        self.toolbox.register("individual", tools.initCycle, creator.Individual,
                             (self.toolbox.attr_fast, self.toolbox.attr_slow, self.toolbox.attr_signal,
                              self.toolbox.attr_rsi_win, self.toolbox.attr_rsi_low, self.toolbox.attr_rsi_high),
                             n=1)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        
        # Operators
        self.toolbox.register("evaluate", self._evaluate_wrapper)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", tools.mutUniformInt, low=[5, 21, 5, 10, 20, 60], 
                              up=[20, 60, 15, 30, 40, 80], indpb=self.mutation_rate)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
        # 교차 후 범위를 벗어나는 경우는 evaluator에서 페널티로 처리

    def _evaluate_wrapper(self, individual):
        """DEAP evaluate wrapper"""
        # evaluator returns (sharpe, )
        return self.evaluator.evaluate(self.df, individual, strategy_type='MACD_RSI')

    def run(self) -> Tuple[List[float], float, object]:
        """최적화 실행. (best_params, best_fitness, logbook) 튜플을 반환"""
        if self.df is None or self.df.empty:
            logger.error("최적화에 필요한 DataFrame이 없거나 비어 있습니다.")
            return [], 0.0, None

        try:
            pop = self.toolbox.population(n=self.pop_size)
            hof = tools.HallOfFame(1)

            # 세대별 통계 (avg, min, max fitness)
            stats = tools.Statistics(lambda ind: ind.fitness.values)
            stats.register("avg", np.mean)
            stats.register("min", np.min)
            stats.register("max", np.max)

            # 진화 알고리즘 실행
            pop, log = algorithms.eaSimple(
                pop, self.toolbox,
                cxpb=0.5, mutpb=self.mutation_rate,
                ngen=self.ngen, stats=stats, halloffame=hof,
                verbose=True
            )

            best_ind = hof[0]
            logger.info(f"최적 개체: {best_ind}, Fitness: {best_ind.fitness.values[0]}")

            return list(best_ind), best_ind.fitness.values[0], log

        except Exception as e:
            logger.error(f"최적화 실패: {e}")
            return [], 0.0, None

    def evolve(
        self,
        symbol: str | None = None,
        df: Optional[pd.DataFrame] = None,
        progress_callback=None,
    ) -> dict:
        """대시보드 친화적인 run() 래퍼. history 포함 결과 dict 반환."""
        if df is not None:
            self.df = df

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

        return {
            "symbol": symbol,
            "best_params": best_params,
            "best_fitness": float(best_fitness),
            "population_size": self.pop_size,
            "generations": self.ngen,
            "mutation_rate": self.mutation_rate,
            "history": history,
        }

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
