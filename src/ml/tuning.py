"""ML 파라미터 튜닝 및 Walk-Forward 백테스트

주요 기능:
- GridSearchCV / RandomizedSearchCV 기반 파라미터 튜닝
- TimeSeriesSplit 기반 시계열 교차검증
- Walk-Forward 백테스트 (실전적 검증)
- 성과 리포트 생성
"""

import numpy as np
import pandas as pd
import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# sklearn 체크
try:
    from sklearn.model_selection import (
        GridSearchCV, RandomizedSearchCV, TimeSeriesSplit,
        cross_val_score
    )
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


@dataclass
class TuningResult:
    """튜닝 결과"""
    best_params: Dict[str, Any]
    best_score: float
    cv_results: Dict[str, Any]
    all_params_tested: int
    time_elapsed: float
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class WalkForwardResult:
    """Walk-Forward 백테스트 결과"""
    periods: List[Dict]
    total_return: float
    avg_return: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class ParameterTuner:
    """ML 모델 파라미터 튜너
    
    GridSearchCV 및 RandomizedSearchCV를 사용하여 최적 파라미터를 탐색합니다.
    """
    
    # 기본 파라미터 그리드
    DEFAULT_PARAM_GRIDS = {
        'RandomForest': {
            'n_estimators': [50, 100, 200],
            'max_depth': [5, 10, 15, None],
            'min_samples_split': [2, 5, 10],
            'min_samples_leaf': [1, 2, 4]
        },
        'GradientBoosting': {
            'n_estimators': [50, 100, 200],
            'max_depth': [3, 5, 7],
            'learning_rate': [0.01, 0.1, 0.2],
            'subsample': [0.8, 1.0]
        },
        'XGBoost': {
            'n_estimators': [50, 100, 200],
            'max_depth': [3, 5, 7],
            'learning_rate': [0.01, 0.1, 0.2],
            'subsample': [0.7, 0.8, 1.0],
            'colsample_bytree': [0.7, 0.8, 1.0]
        }
    }
    
    def __init__(self, n_splits: int = 5, scoring: str = 'accuracy'):
        """초기화
        
        Args:
            n_splits: 교차검증 분할 수
            scoring: 평가 지표 ('accuracy', 'f1', 'precision', 'recall')
        """
        self.n_splits = n_splits
        self.scoring = scoring
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        
    def tune_grid_search(
        self, 
        model, 
        X: np.ndarray, 
        y: np.ndarray,
        param_grid: Dict[str, List] = None,
        use_time_series_split: bool = True
    ) -> TuningResult:
        """GridSearchCV 기반 파라미터 튜닝
        
        Args:
            model: sklearn 모델
            X: 피처 데이터
            y: 레이블
            param_grid: 탐색할 파라미터 그리드
            use_time_series_split: 시계열 분할 사용 여부
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn이 필요합니다.")
        
        import time
        start_time = time.time()
        
        # 기본 파라미터 그리드
        if param_grid is None:
            model_name = model.__class__.__name__
            param_grid = self.DEFAULT_PARAM_GRIDS.get(model_name, {})
        
        # 교차검증 방식
        if use_time_series_split:
            cv = TimeSeriesSplit(n_splits=self.n_splits)
        else:
            cv = self.n_splits
        
        # GridSearchCV 실행
        grid_search = GridSearchCV(
            model,
            param_grid,
            cv=cv,
            scoring=self.scoring,
            n_jobs=-1,
            verbose=1
        )
        
        # 스케일링
        X_scaled = self.scaler.fit_transform(X)
        
        grid_search.fit(X_scaled, y)
        
        elapsed = time.time() - start_time
        
        result = TuningResult(
            best_params=grid_search.best_params_,
            best_score=grid_search.best_score_,
            cv_results={k: v.tolist() if hasattr(v, 'tolist') else v 
                       for k, v in grid_search.cv_results_.items()},
            all_params_tested=len(grid_search.cv_results_['params']),
            time_elapsed=elapsed
        )
        
        logger.info(f"GridSearchCV 완료: 최적 점수 {result.best_score:.4f}")
        logger.info(f"최적 파라미터: {result.best_params}")
        
        return result
    
    def tune_random_search(
        self,
        model,
        X: np.ndarray,
        y: np.ndarray,
        param_distributions: Dict[str, Any] = None,
        n_iter: int = 50,
        use_time_series_split: bool = True
    ) -> TuningResult:
        """RandomizedSearchCV 기반 파라미터 튜닝 (빠른 탐색)
        
        Args:
            model: sklearn 모델
            X: 피처
            y: 레이블
            param_distributions: 파라미터 분포
            n_iter: 탐색 횟수
            use_time_series_split: 시계열 분할 사용
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn이 필요합니다.")
        
        import time
        from scipy.stats import randint, uniform
        
        start_time = time.time()
        
        # 기본 분포  
        if param_distributions is None:
            param_distributions = {
                'n_estimators': randint(50, 300),
                'max_depth': randint(3, 20),
                'min_samples_split': randint(2, 20),
                'min_samples_leaf': randint(1, 10)
            }
        
        if use_time_series_split:
            cv = TimeSeriesSplit(n_splits=self.n_splits)
        else:
            cv = self.n_splits
        
        random_search = RandomizedSearchCV(
            model,
            param_distributions,
            n_iter=n_iter,
            cv=cv,
            scoring=self.scoring,
            n_jobs=-1,
            random_state=42,
            verbose=1
        )
        
        X_scaled = self.scaler.fit_transform(X)
        random_search.fit(X_scaled, y)
        
        elapsed = time.time() - start_time
        
        result = TuningResult(
            best_params=random_search.best_params_,
            best_score=random_search.best_score_,
            cv_results={k: v.tolist() if hasattr(v, 'tolist') else v 
                       for k, v in random_search.cv_results_.items()},
            all_params_tested=n_iter,
            time_elapsed=elapsed
        )
        
        logger.info(f"RandomizedSearchCV 완료: 최적 점수 {result.best_score:.4f}")
        
        return result
    
    def save_result(self, result: TuningResult, filepath: str):
        """튜닝 결과 저장"""
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(result), f, ensure_ascii=False, indent=2, default=str)


class WalkForwardBacktester:
    """Walk-Forward 백테스터
    
    일정 기간마다 모델을 재학습하여 실전에 가깝게 테스트합니다.
    """
    
    def __init__(
        self,
        train_period: int = 252,   # 1년 (거래일)
        test_period: int = 21,     # 1개월
        retrain_interval: int = 21, # 재학습 주기
        commission_rate: float = 0.00015
    ):
        """초기화
        
        Args:
            train_period: 학습 기간 (일)
            test_period: 테스트 기간 (일)
            retrain_interval: 재학습 간격 (일)
            commission_rate: 거래 수수료율
        """
        self.train_period = train_period
        self.test_period = test_period
        self.retrain_interval = retrain_interval
        self.commission_rate = commission_rate
    
    def run(
        self,
        df: pd.DataFrame,
        strategy,    # MLStrategy 인스턴스
        initial_capital: float = 10_000_000
    ) -> WalkForwardResult:
        """Walk-Forward 백테스트 실행
        
        Args:
            df: OHLCV 데이터 (date, open, high, low, close, volume)
            strategy: ML 전략 (train, generate_signals 메서드 필요)
            initial_capital: 초기 자본
        """
        df = df.reset_index(drop=True)
        periods = []
        
        capital = initial_capital
        total_trades = 0
        win_trades = 0
        returns = []
        
        # Walk-Forward 루프
        start_idx = 0
        while start_idx + self.train_period + self.test_period <= len(df):
            # 구간 정의
            train_start = start_idx
            train_end = start_idx + self.train_period
            test_start = train_end
            test_end = min(test_start + self.test_period, len(df))
            
            # 학습
            train_df = df.iloc[train_start:train_end].copy()
            accuracy = strategy.train(train_df)
            
            # 테스트 (매일 신호 생성)
            test_df = df.iloc[test_start:test_end].copy()
            period_return = 0
            period_trades = 0
            period_wins = 0
            
            position = 0  # 0: 없음, 1: 롱
            entry_price = 0
            
            for i in range(len(test_df)):
                # 신호 생성 (학습 데이터 + 현재까지 테스트 데이터)
                current_df = pd.concat([train_df, test_df.iloc[:i+1]])
                signals = strategy.generate_signals(current_df)
                signal = signals['signal'].iloc[-1]
                
                current_price = test_df.iloc[i]['close']
                
                # 포지션 관리
                if signal == 1 and position == 0:
                    # 매수
                    position = 1
                    entry_price = current_price * (1 + self.commission_rate)
                    period_trades += 1
                    
                elif signal == -1 and position == 1:
                    # 매도
                    exit_price = current_price * (1 - self.commission_rate)
                    trade_return = (exit_price - entry_price) / entry_price
                    period_return += trade_return
                    
                    if trade_return > 0:
                        period_wins += 1
                    
                    position = 0
                    entry_price = 0
            
            # 미청산 포지션 정리
            if position == 1:
                exit_price = test_df.iloc[-1]['close'] * (1 - self.commission_rate)
                trade_return = (exit_price - entry_price) / entry_price
                period_return += trade_return
                if trade_return > 0:
                    period_wins += 1
            
            # 기간 결과 저장
            period_info = {
                'train_start': str(train_df.iloc[0].get('date', train_start)),
                'train_end': str(train_df.iloc[-1].get('date', train_end)),
                'test_start': str(test_df.iloc[0].get('date', test_start)),
                'test_end': str(test_df.iloc[-1].get('date', test_end)),
                'return_pct': period_return * 100,
                'trades': period_trades,
                'wins': period_wins,
                'accuracy': accuracy
            }
            periods.append(period_info)
            
            capital *= (1 + period_return)
            returns.append(period_return)
            total_trades += period_trades
            win_trades += period_wins
            
            logger.info(f"기간 {len(periods)}: 수익률 {period_return*100:+.2f}%, 거래 {period_trades}건")
            
            # 다음 기간으로 이동
            start_idx += self.retrain_interval
        
        # 전체 통계 계산
        total_return = (capital - initial_capital) / initial_capital
        avg_return = np.mean(returns) if returns else 0
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 샤프 비율 (연율화)
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # 최대 낙폭
        cumulative = np.cumprod([1 + r for r in returns])
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_drawdown = abs(min(drawdowns)) if len(drawdowns) > 0 else 0
        
        result = WalkForwardResult(
            periods=periods,
            total_return=total_return * 100,
            avg_return=avg_return * 100,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown * 100,
            total_trades=total_trades
        )
        
        logger.info(f"Walk-Forward 완료: 총 수익률 {result.total_return:.2f}%, 샤프 {result.sharpe_ratio:.2f}")
        
        return result
    
    def generate_report(self, result: WalkForwardResult) -> str:
        """성과 리포트 생성"""
        report = f"""
📊 Walk-Forward 백테스트 리포트
{'='*50}

💰 성과 요약
• 총 수익률: {result.total_return:+.2f}%
• 평균 기간 수익률: {result.avg_return:+.2f}%
• 승률: {result.win_rate:.1f}%
• 샤프 비율: {result.sharpe_ratio:.2f}
• 최대 낙폭: {result.max_drawdown:.2f}%
• 총 거래 횟수: {result.total_trades}건

{'='*50}
📅 기간별 상세
{'='*50}
"""
        for i, period in enumerate(result.periods, 1):
            emoji = "📈" if period['return_pct'] > 0 else "📉"
            report += f"""
{i}. {period['test_start']} ~ {period['test_end']}
   {emoji} 수익률: {period['return_pct']:+.2f}% | 거래: {period['trades']}건 | 모델 정확도: {period['accuracy']:.2%}
"""
        
        return report
    
    def save_result(self, result: WalkForwardResult, filepath: str):
        """결과 저장"""
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(result), f, ensure_ascii=False, indent=2)
