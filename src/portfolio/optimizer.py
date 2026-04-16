"""포트폴리오 최적화
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional
from scipy.optimize import minimize

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """Markowitz Mean-Variance 포트폴리오 최적화"""
    
    def __init__(self, returns_df: pd.DataFrame, risk_free_rate: float = 0.035):
        """
        Args:
            returns_df: 일별 수익률 데이터프레임 (종목별 컬럼)
            risk_free_rate: 무위험 수익률 (연율)
        """
        self.returns = returns_df
        self.rf_rate = risk_free_rate
        self.n_assets = len(returns_df.columns)
        self.tickers = returns_df.columns.tolist()
        
    def optimize_sharpe_ratio(self) -> Dict[str, float]:
        """Sharpe Ratio 최대가 되는 포트폴리오 비중 계산"""
        if self.returns.empty:
            return {}
            
        mean_ret = self.returns.mean() * 252 # 연율화
        cov_mat = self.returns.cov() * 252   # 연율화
        
        def sharpe_ratio(weights):
            p_ret = np.sum(mean_ret * weights)
            p_vol = np.sqrt(np.dot(weights.T, np.dot(cov_mat, weights)))
            return - (p_ret - self.rf_rate) / p_vol # Minimize negative Sharpe
        
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0.0, 1.0) for _ in range(self.n_assets))
        initial_w = np.array([1. / self.n_assets] * self.n_assets)
        
        try:
            result = minimize(sharpe_ratio, initial_w, method='SLSQP', bounds=bounds, constraints=constraints)
            
            if result.success:
                weights = result.x
                return {ticker: round(weight, 4) for ticker, weight in zip(self.tickers, weights) if weight > 0.01}
            else:
                logger.warning(f"최적화 실패: {result.message}")
                return self._equal_weights()
                
        except Exception as e:
            logger.error(f"최적화 중 오류 발생: {e}")
            return self._equal_weights()

    def optimize_min_variance(self) -> Dict[str, float]:
        """변동성 최소가 되는 포트폴리오 비중 계산"""
        if self.returns.empty:
            return {}
            
        cov_mat = self.returns.cov() * 252
        
        def portfolio_volatility(weights):
            return np.sqrt(np.dot(weights.T, np.dot(cov_mat, weights)))
            
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0.0, 1.0) for _ in range(self.n_assets))
        initial_w = np.array([1. / self.n_assets] * self.n_assets)
        
        try:
            result = minimize(portfolio_volatility, initial_w, method='SLSQP', bounds=bounds, constraints=constraints)
            
            if result.success:
                weights = result.x
                return {ticker: round(weight, 4) for ticker, weight in zip(self.tickers, weights) if weight > 0.01}
            else:
                return self._equal_weights()
        except Exception:
            return self._equal_weights()
            
    def _equal_weights(self) -> Dict[str, float]:
        """균등 비중 반환"""
        w = round(1.0 / self.n_assets, 4)
        return {ticker: w for ticker in self.tickers}
