"""백테스팅 엔진

과거 데이터를 사용하여 매매 전략을 시뮬레이션하고 성과를 분석합니다.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, TYPE_CHECKING
from src.data.models import Position, OrderSide
from src.strategies.base import BaseStrategy

# Exit 전략 임포트 (선택적)
try:
    from src.strategies.exit_base import BaseExitStrategy, PositionContext, ExitSignal
    from src.strategies.exit_strategies import calculate_atr
    EXIT_STRATEGY_AVAILABLE = True
except ImportError:
    EXIT_STRATEGY_AVAILABLE = False


@dataclass
class Trade:
    """거래 기록"""
    symbol: str
    side: OrderSide
    price: float
    quantity: int
    commission: float
    timestamp: datetime


@dataclass
class BacktestResult:
    """백테스팅 결과"""
    total_return: float
    cagr: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    trades: List[Trade]
    portfolio_history: pd.DataFrame
    portfolio: 'Portfolio'


class Portfolio:
    """백테스팅 포트폴리오 관리"""
    
    def __init__(self, initial_capital: float = 10000000, commission_rate: float = 0.00015):
        """초기화
        
        Args:
            initial_capital: 초기 자본금
            commission_rate: 수수료율 (기본 0.015%)
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.commission_rate = commission_rate
        self.history: List[Dict] = []
        self.trades: List[Trade] = []
        
    @property
    def total_value(self) -> float:
        """총 자산 가치 (현금 + 포지션 평가액)"""
        positions_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash + positions_value
        
    def update_position(self, symbol: str, quantity: int, price: float, side: OrderSide, timestamp: datetime):
        """포지션 업데이트 (매수/매도)"""
        cost = quantity * price
        commission = cost * self.commission_rate
        total_cost = cost + commission
        
        if side == OrderSide.BUY:
            if self.cash < total_cost:
                raise ValueError(f"현금 부족: 필요 {total_cost}, 보유 {self.cash}")
            
            self.cash -= total_cost
            
            if symbol in self.positions:
                # 추가 매수: 평균단가 갱신
                current_pos = self.positions[symbol]
                new_quantity = current_pos.quantity + quantity
                new_avg_price = ((current_pos.avg_price * current_pos.quantity) + cost) / new_quantity
                
                current_pos.quantity = new_quantity
                current_pos.avg_price = new_avg_price
                current_pos.current_price = price
            else:
                # 신규 매수
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price,
                    current_price=price
                )
                
        elif side == OrderSide.SELL:
            if symbol not in self.positions or self.positions[symbol].quantity < quantity:
                raise ValueError(f"매도 수량 부족: 보유 {self.positions.get(symbol, 0).quantity if symbol in self.positions else 0}")
            
            # 매도 대금 수령 (세금 등은 일단 제외하고 수수료만 계산)
            proceeds = cost - commission
            self.cash += proceeds
            
            current_pos = self.positions[symbol]
            current_pos.quantity -= quantity
            current_pos.current_price = price
            
            if current_pos.quantity == 0:
                del self.positions[symbol]
                
        # 거래 기록
        trade = Trade(
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            commission=commission,
            timestamp=timestamp
        )
        self.trades.append(trade)

    def update_market_value(self, current_prices: Dict[str, float]):
        """현재가 업데이트"""
        for symbol, price in current_prices.items():
            if symbol in self.positions:
                self.positions[symbol].current_price = price

    def record_history(self, timestamp: datetime):
        """히스토리 기록"""
        self.history.append({
            'timestamp': timestamp,
            'total_value': self.total_value,
            'cash': self.cash
        })


class BacktestEngine:
    """백테스팅 실행 엔진"""
    
    def __init__(
        self,
        strategy: BaseStrategy,
        symbol: str,
        data: pd.DataFrame,
        initial_capital: float = 10000000,
        exit_strategy: 'BaseExitStrategy' = None,
        position_size_pct: float = 0.95
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.data = data
        self.initial_capital = initial_capital
        self.portfolio = Portfolio(initial_capital)
        self.exit_strategy = exit_strategy
        self.position_size_pct = position_size_pct
        self._high_water_marks: Dict[str, float] = {}
        self._entry_dates: Dict[str, datetime] = {}
        self._atr_series: Optional[pd.Series] = None
        
        # ATR 미리 계산 (exit 전략에서 사용)
        if EXIT_STRATEGY_AVAILABLE and exit_strategy is not None:
            self._atr_series = calculate_atr(data)
        
    def run(self) -> BacktestResult:
        """백테스트 실행"""
        # 전략 신호 생성
        signals = self.strategy.generate_signals(self.data)
        
        # 데이터 순회하며 시뮬레이션
        for i in range(len(self.data)):
            date = self.data['datetime'].iloc[i]
            price = self.data['close'].iloc[i]
            signal = signals['signal'].iloc[i]
            
            # 현재가 업데이트
            self.portfolio.update_market_value({self.symbol: price})
            
            # Exit 전략 체크 (신호보다 우선)
            if self._check_exit_strategy(i, date, price):
                self.portfolio.record_history(date)
                continue
            
            # 신호 처리
            if signal == 1:  # 매수 신호
                # 가용 자금의 설정 비율 투자
                target_amount = self.portfolio.cash * self.position_size_pct
                quantity = int(target_amount // price)
                
                if quantity > 0:
                    try:
                        self.portfolio.update_position(
                            self.symbol, quantity, price, OrderSide.BUY, date
                        )
                        # 진입일 기록
                        self._entry_dates[self.symbol] = date
                        self._high_water_marks[self.symbol] = price
                        
                        # Exit 전략 초기화
                        if self.exit_strategy:
                            self.exit_strategy.reset()
                    except ValueError:
                        pass # 자금 부족 등은 무시하고 진행
                        
            elif signal == -1:  # 매도 신호
                if self.symbol in self.portfolio.positions:
                    quantity = self.portfolio.positions[self.symbol].quantity
                    if quantity > 0:
                        self.portfolio.update_position(
                            self.symbol, quantity, price, OrderSide.SELL, date
                        )
                        # 청산 시 상태 정리
                        self._entry_dates.pop(self.symbol, None)
                        self._high_water_marks.pop(self.symbol, None)
            
            # High Water Mark 업데이트
            if self.symbol in self.portfolio.positions:
                current_hwm = self._high_water_marks.get(self.symbol, price)
                if price > current_hwm:
                    self._high_water_marks[self.symbol] = price
            
            # 일별 기록
            self.portfolio.record_history(date)
            
        return self._calculate_performance()
    
    def _check_exit_strategy(self, idx: int, date: datetime, price: float) -> bool:
        """Exit 전략 체크 및 실행
        
        Returns:
            True if exit was executed, False otherwise
        """
        if not EXIT_STRATEGY_AVAILABLE or self.exit_strategy is None:
            return False
        
        if self.symbol not in self.portfolio.positions:
            return False
        
        position = self.portfolio.positions[self.symbol]
        if position.quantity <= 0:
            return False
        
        # PositionContext 생성
        entry_date = self._entry_dates.get(self.symbol)
        holding_days = (date - entry_date).days if entry_date else 0
        
        atr_value = 0.0
        if self._atr_series is not None and idx < len(self._atr_series):
            atr_value = self._atr_series.iloc[idx]
        
        context = PositionContext(
            symbol=self.symbol,
            quantity=position.quantity,
            avg_price=position.avg_price,
            current_price=price,
            high_water_mark=self._high_water_marks.get(self.symbol, price),
            atr=atr_value,
            holding_days=holding_days,
            entry_date=entry_date
        )
        
        # Exit 전략에 상태 업데이트
        market_data = self.data.iloc[idx]
        self.exit_strategy.update(context, market_data)
        
        # Exit 신호 체크
        signal = self.exit_strategy.check_exit(context, market_data)
        
        if signal.should_exit:
            # 청산 수량 계산
            exit_quantity = int(position.quantity * signal.exit_ratio)
            if exit_quantity > 0:
                self.portfolio.update_position(
                    self.symbol, exit_quantity, price, OrderSide.SELL, date
                )
                
                # 전량 청산인 경우 상태 정리
                if signal.exit_ratio >= 1.0 or self.symbol not in self.portfolio.positions:
                    self._entry_dates.pop(self.symbol, None)
                    self._high_water_marks.pop(self.symbol, None)
                
                return True
        
        return False
    
    def _calculate_performance(self) -> BacktestResult:
        """성과 지표 계산"""
        history_df = pd.DataFrame(self.portfolio.history)
        history_df.set_index('timestamp', inplace=True)
        
        # 수익률
        final_value = self.portfolio.total_value
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        # 일별 수익률
        daily_returns = history_df['total_value'].pct_change().dropna()
        
        # 샤프 비율 (무위험수익률 0 가정)
        if len(daily_returns) > 0 and daily_returns.std() != 0:
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std()
        else:
            sharpe_ratio = 0.0
            
        # MDD
        rolling_max = history_df['total_value'].cummax()
        drawdown = history_df['total_value'] / rolling_max - 1.0
        max_drawdown = drawdown.min() * 100
        
        # CAGR 계산
        total_days = len(self.data)
        if total_days > 0 and self.initial_capital > 0 and final_value > 0:
            cagr = (final_value / self.initial_capital) ** (252 / total_days) - 1
        else:
            cagr = 0.0

        # 승률 계산 (매수-매도 쌍 기준)
        trades = self.portfolio.trades
        buy_prices: Dict[str, float] = {}
        winning_trades = 0
        total_closed_trades = 0
        for trade in trades:
            if trade.side == OrderSide.BUY:
                buy_prices[trade.symbol] = trade.price
            elif trade.side == OrderSide.SELL and trade.symbol in buy_prices:
                total_closed_trades += 1
                if trade.price > buy_prices[trade.symbol]:
                    winning_trades += 1
                buy_prices.pop(trade.symbol, None)
        win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0.0

        return BacktestResult(
            total_return=total_return,
            cagr=cagr,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            trades=self.portfolio.trades,
            portfolio_history=history_df,
            portfolio=self.portfolio
        )
