"""호가창 분석 (Order Flow Intelligence) 모듈

실시간 호가창 데이터를 분석하여 기관/외국인 매매 방향을 예측합니다.

주요 기능:
1. 호가 불균형(Order Book Imbalance) 분석
2. 대량 주문 감지
3. 거래량 가중 평균 가격(VWAP) 계산
4. 매수/매도 압력 지표
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import numpy as np

logger = logging.getLogger("OrderFlowIntelligence")


class MarketSide(Enum):
    """시장 방향"""
    BULLISH = "상승"
    BEARISH = "하락"
    NEUTRAL = "중립"


@dataclass
class OrderBookLevel:
    """호가 단계"""
    price: float
    quantity: int
    order_count: int = 0  # 주문 건수 (한투 WebSocket 제공 시)


@dataclass
class OrderBook:
    """호가창 데이터"""
    symbol: str
    timestamp: datetime
    asks: List[OrderBookLevel]  # 매도호가 (낮은 가격순)
    bids: List[OrderBookLevel]  # 매수호가 (높은 가격순)
    
    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """최우선 매도호가"""
        return self.asks[0] if self.asks else None
    
    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """최우선 매수호가"""
        return self.bids[0] if self.bids else None
    
    @property
    def spread(self) -> float:
        """스프레드 (호가 차이)"""
        if self.best_ask and self.best_bid:
            return self.best_ask.price - self.best_bid.price
        return 0.0
    
    @property
    def spread_pct(self) -> float:
        """스프레드 비율 (%)"""
        if self.best_bid and self.best_bid.price > 0:
            return self.spread / self.best_bid.price * 100
        return 0.0


@dataclass
class TradeExecution:
    """체결 데이터"""
    symbol: str
    price: float
    quantity: int
    side: str  # "BUY" or "SELL"
    timestamp: datetime


class OrderFlowAnalyzer:
    """호가창 분석기"""
    
    def __init__(self, lookback_trades: int = 100):
        self.lookback_trades = lookback_trades
        self._trade_history: Dict[str, List[TradeExecution]] = {}
        self._orderbook_history: Dict[str, List[OrderBook]] = {}
    
    def add_orderbook(self, orderbook: OrderBook):
        """호가창 데이터 추가"""
        if orderbook.symbol not in self._orderbook_history:
            self._orderbook_history[orderbook.symbol] = []
        
        history = self._orderbook_history[orderbook.symbol]
        history.append(orderbook)
        
        # 최근 100개만 유지
        if len(history) > 100:
            self._orderbook_history[orderbook.symbol] = history[-100:]
    
    def add_trade(self, trade: TradeExecution):
        """체결 데이터 추가"""
        if trade.symbol not in self._trade_history:
            self._trade_history[trade.symbol] = []
        
        history = self._trade_history[trade.symbol]
        history.append(trade)
        
        # lookback 개수만 유지
        if len(history) > self.lookback_trades:
            self._trade_history[trade.symbol] = history[-self.lookback_trades:]
    
    def calculate_imbalance(self, orderbook: OrderBook, levels: int = 5) -> float:
        """
        호가 불균형 계산
        
        Args:
            orderbook: 호가창 데이터
            levels: 분석할 호가 단계 수 (기본 5단계)
            
        Returns:
            불균형 비율 (-1 ~ 1)
            - 양수: 매수 우세 (상승 압력)
            - 음수: 매도 우세 (하락 압력)
        """
        if not orderbook.asks or not orderbook.bids:
            return 0.0
        
        # 상위 N개 호가의 수량 합계
        ask_qty = sum(level.quantity for level in orderbook.asks[:levels])
        bid_qty = sum(level.quantity for level in orderbook.bids[:levels])
        
        total = ask_qty + bid_qty
        if total == 0:
            return 0.0
        
        # 불균형 비율: (Bid - Ask) / (Bid + Ask)
        imbalance = (bid_qty - ask_qty) / total
        
        return imbalance
    
    def calculate_weighted_imbalance(self, orderbook: OrderBook, levels: int = 5) -> float:
        """
        가격 가중 호가 불균형 계산
        
        멀리 있는 호가보다 가까운 호가에 더 높은 가중치 부여
        """
        if not orderbook.asks or not orderbook.bids or not orderbook.best_bid:
            return 0.0
        
        mid_price = (orderbook.best_ask.price + orderbook.best_bid.price) / 2 if orderbook.best_ask else orderbook.best_bid.price
        
        weighted_bid = 0.0
        weighted_ask = 0.0
        
        for i, level in enumerate(orderbook.bids[:levels]):
            # 거리가 가까울수록 높은 가중치
            distance = abs(level.price - mid_price) / mid_price
            weight = 1.0 / (1.0 + distance * 100)
            weighted_bid += level.quantity * weight
        
        for i, level in enumerate(orderbook.asks[:levels]):
            distance = abs(level.price - mid_price) / mid_price
            weight = 1.0 / (1.0 + distance * 100)
            weighted_ask += level.quantity * weight
        
        total = weighted_bid + weighted_ask
        if total == 0:
            return 0.0
        
        return (weighted_bid - weighted_ask) / total
    
    def detect_large_orders(
        self, 
        orderbook: OrderBook, 
        threshold_multiplier: float = 3.0
    ) -> List[Dict]:
        """
        대량 주문 감지
        
        Args:
            orderbook: 호가창 데이터
            threshold_multiplier: 평균 대비 배수 기준 (기본 3배)
            
        Returns:
            대량 주문 정보 리스트
        """
        all_levels = orderbook.asks + orderbook.bids
        if not all_levels:
            return []
        
        quantities = [level.quantity for level in all_levels]
        mean_qty = np.mean(quantities)
        std_qty = np.std(quantities)
        
        threshold = mean_qty + threshold_multiplier * std_qty
        
        large_orders = []
        
        for level in orderbook.bids:
            if level.quantity > threshold:
                large_orders.append({
                    "side": "BID",
                    "price": level.price,
                    "quantity": level.quantity,
                    "z_score": (level.quantity - mean_qty) / std_qty if std_qty > 0 else 0
                })
        
        for level in orderbook.asks:
            if level.quantity > threshold:
                large_orders.append({
                    "side": "ASK",
                    "price": level.price,
                    "quantity": level.quantity,
                    "z_score": (level.quantity - mean_qty) / std_qty if std_qty > 0 else 0
                })
        
        return large_orders
    
    def calculate_vwap(self, symbol: str) -> float:
        """
        VWAP (거래량 가중 평균 가격) 계산
        
        Args:
            symbol: 종목 코드
            
        Returns:
            VWAP 값
        """
        trades = self._trade_history.get(symbol, [])
        if not trades:
            return 0.0
        
        total_value = sum(t.price * t.quantity for t in trades)
        total_volume = sum(t.quantity for t in trades)
        
        if total_volume == 0:
            return 0.0
        
        return total_value / total_volume
    
    def calculate_buy_sell_pressure(self, symbol: str) -> Tuple[float, float]:
        """
        매수/매도 압력 계산
        
        Returns:
            (매수 압력, 매도 압력) - 각각 0 ~ 1 사이
        """
        trades = self._trade_history.get(symbol, [])
        if not trades:
            return 0.5, 0.5
        
        buy_volume = sum(t.quantity for t in trades if t.side == "BUY")
        sell_volume = sum(t.quantity for t in trades if t.side == "SELL")
        
        total = buy_volume + sell_volume
        if total == 0:
            return 0.5, 0.5
        
        buy_pressure = buy_volume / total
        sell_pressure = sell_volume / total
        
        return buy_pressure, sell_pressure
    
    def predict_direction(self, orderbook: OrderBook) -> Dict:
        """
        시장 방향 예측
        
        Args:
            orderbook: 호가창 데이터
            
        Returns:
            예측 결과
        """
        imbalance = self.calculate_imbalance(orderbook)
        weighted_imbalance = self.calculate_weighted_imbalance(orderbook)
        large_orders = self.detect_large_orders(orderbook)
        
        # 매수/매도 압력
        buy_pressure, sell_pressure = self.calculate_buy_sell_pressure(orderbook.symbol)
        
        # 종합 점수 계산
        # 가중치: 불균형 40%, 가중 불균형 30%, 체결 압력 30%
        score = (
            imbalance * 0.4 +
            weighted_imbalance * 0.3 +
            (buy_pressure - sell_pressure) * 0.3
        )
        
        # 대량 주문 조정
        if large_orders:
            bid_large = sum(1 for o in large_orders if o["side"] == "BID")
            ask_large = sum(1 for o in large_orders if o["side"] == "ASK")
            
            if bid_large > ask_large:
                score += 0.1
            elif ask_large > bid_large:
                score -= 0.1
        
        # 방향 결정
        if score > 0.15:
            direction = MarketSide.BULLISH
            confidence = min(abs(score), 1.0)
        elif score < -0.15:
            direction = MarketSide.BEARISH
            confidence = min(abs(score), 1.0)
        else:
            direction = MarketSide.NEUTRAL
            confidence = 0.3
        
        return {
            "symbol": orderbook.symbol,
            "direction": direction,
            "confidence": confidence,
            "imbalance": imbalance,
            "weighted_imbalance": weighted_imbalance,
            "buy_pressure": buy_pressure,
            "sell_pressure": sell_pressure,
            "large_orders": len(large_orders),
            "score": score,
            "timestamp": orderbook.timestamp.isoformat()
        }


class OrderFlowMonitor:
    """호가창 실시간 모니터
    
    WebSocket 데이터와 연동하여 실시간 분석을 제공합니다.
    """
    
    def __init__(self, watch_list: List[str] = None):
        self.analyzer = OrderFlowAnalyzer()
        self.watch_list = watch_list or []
        self._alerts: List[Dict] = []
    
    def on_orderbook_update(self, orderbook: OrderBook):
        """호가창 업데이트 콜백"""
        if self.watch_list and orderbook.symbol not in self.watch_list:
            return
        
        self.analyzer.add_orderbook(orderbook)
        
        # 분석 수행
        prediction = self.analyzer.predict_direction(orderbook)
        
        # 강한 시그널 감지 시 알림
        if prediction["confidence"] > 0.7:
            alert = {
                "type": "STRONG_SIGNAL",
                "symbol": orderbook.symbol,
                "direction": prediction["direction"].value,
                "confidence": prediction["confidence"],
                "timestamp": prediction["timestamp"]
            }
            self._alerts.append(alert)
            logger.info(f"강한 시그널 감지: {alert}")
        
        # 대량 주문 감지 시 알림
        large_orders = self.analyzer.detect_large_orders(orderbook)
        if large_orders:
            alert = {
                "type": "LARGE_ORDER",
                "symbol": orderbook.symbol,
                "orders": large_orders,
                "timestamp": orderbook.timestamp.isoformat()
            }
            self._alerts.append(alert)
            logger.info(f"대량 주문 감지: {alert}")
    
    def on_trade_execution(self, trade: TradeExecution):
        """체결 데이터 콜백"""
        if self.watch_list and trade.symbol not in self.watch_list:
            return
        
        self.analyzer.add_trade(trade)
    
    def get_alerts(self, clear: bool = True) -> List[Dict]:
        """알림 조회"""
        alerts = self._alerts.copy()
        if clear:
            self._alerts = []
        return alerts
    
    def get_analysis(self, symbol: str) -> Optional[Dict]:
        """특정 종목 분석 결과 조회"""
        orderbooks = self.analyzer._orderbook_history.get(symbol, [])
        if not orderbooks:
            return None
        
        latest = orderbooks[-1]
        return self.analyzer.predict_direction(latest)


# 전역 인스턴스
_global_monitor: Optional[OrderFlowMonitor] = None


def get_orderflow_monitor(watch_list: List[str] = None) -> OrderFlowMonitor:
    """전역 호가창 모니터 인스턴스 반환"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = OrderFlowMonitor(watch_list=watch_list)
    return _global_monitor
