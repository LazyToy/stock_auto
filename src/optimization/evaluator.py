import pandas as pd
import numpy as np
import logging
from typing import List, Tuple, Union

logger = logging.getLogger("StrategyEvaluator")

class StrategyEvaluator:
    """
    유전자 알고리즘을 위한 고속 전략 평가기
    - Vectorized operations for speed
    """
    
    def __init__(self, initial_capital=10000000, fee=0.0015):
        self.initial_capital = initial_capital
        self.fee = fee # 0.15%

    def evaluate(self, df: pd.DataFrame, params: List[float], strategy_type: str = 'MACD_RSI') -> Tuple[float]:
        """
        전략 파라미터 평가
        Args:
            df: OHLCV DataFrame
            params: 파라미터 리스트
            strategy_type: 전략 유형
        Returns:
            (Sharpe Ratio, ) - DEAP requires tuple
        """
        if df.empty:
            return (-9999.0,)
            
        try:
            if strategy_type == 'MACD_RSI':
                return self._evaluate_macd_rsi(df, params)
            else:
                return (-9999.0,)
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return (-9999.0,)

    def _evaluate_macd_rsi(self, df: pd.DataFrame, params: List[float]) -> Tuple[float]:
        """
        MACD + RSI 전략 평가 (Vectorized)
        Params: [fast, slow, signal, rsi_window, rsi_lower, rsi_upper]
        """
        # Unpack params (convert to int where necessary)
        n_fast = int(params[0])
        n_slow = int(params[1])
        n_signal = int(params[2])
        n_rsi = int(params[3])
        rsi_lower = params[4]
        rsi_upper = params[5]
        
        # Constraints Check (Penalty)
        if n_fast >= n_slow or n_fast < 2 or n_slow < 5:
            return (-999.0,)
        if rsi_lower >= rsi_upper:
            return (-999.0,)
            
        # Calculate Indicators
        close = df['Close']
        
        # MACD
        ema_fast = close.ewm(span=n_fast, adjust=False).mean()
        ema_slow = close.ewm(span=n_slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=n_signal, adjust=False).mean()
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=n_rsi).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=n_rsi).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # Generate Signals
        # Buy: MACD > Signal AND RSI < Lower
        # Sell: MACD < Signal OR RSI > Upper
        
        # Vectorized Signal Logic
        # 1: Long, 0: Neutral (No Shorting for now)
        signals = pd.Series(0, index=df.index)
        
        buy_cond = (macd > signal) & (rsi < rsi_lower)
        sell_cond = (macd < signal) | (rsi > rsi_upper)
        
        # Apply signals (Need to maintain position state, difficult to fully vectorize with state)
        # However, for GA, we often use simplified "Market Position" check.
        # Or use a fast loop for position management.
        # Pure vectorized approach: 
        # position = buy_cond.astype(int) - sell_cond.astype(int) 
        # accumulated...
        
        # Let's use a fast loop for accuracy of holding period
        # Numba could optimize this, but Python loop is okay for 100-1000 candles
        
        position = 0 # 0: None, 1: Long
        returns = []
        
        # Pre-convert to numpy for speed
        price_arr = close.values
        buy_arr = buy_cond.values
        sell_arr = sell_cond.values
        daily_ret_arr = df['Close'].pct_change().fillna(0).values
        
        strategy_ret = np.zeros_like(daily_ret_arr)
        
        for i in range(1, len(price_arr)):
            if position == 0:
                if buy_arr[i-1]: # Signal from previous day
                    position = 1
                    # Fee deducted from invested capital on entry:
                    # effective return on day i already reduced by fee ratio
                    strategy_ret[i] = daily_ret_arr[i] * (1 - self.fee)
            elif position == 1:
                strategy_ret[i] = daily_ret_arr[i]
                if sell_arr[i-1]: # Signal from previous day
                    position = 0
                    # Fee deducted from proceeds on exit
                    strategy_ret[i] = daily_ret_arr[i] * (1 - self.fee)
        
        # Calculate Metrics
        # Annualized Sharpe Ratio
        # Assuming 252 trading days
        
        mean_ret = np.mean(strategy_ret)
        std_ret = np.std(strategy_ret)
        
        if std_ret == 0:
            return (0.0,)
            
        sharpe = (mean_ret / std_ret) * np.sqrt(252)
        
        return (sharpe,)
