"""실전 매매 엔진

실시간 시세를 모니터링하고 전략에 따라 주문을 실행합니다.
Circuit Breaker 패턴으로 API 연속 실패 시 자동 중단합니다.
"""

import time
import logging
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from src.data.api_client import KISAPIClient
from src.strategies.base import BaseStrategy
from src.live.risk_manager import RiskManager
from src.data.models import Order, OrderType, OrderSide
import pandas as pd

# 시장 시간 체커 import
try:
    from src.utils.market_hours import MarketTimeChecker, MarketSession, get_market_checker
    MARKET_HOURS_AVAILABLE = True
except ImportError:
    MARKET_HOURS_AVAILABLE = False

# Circuit Breaker import
try:
    from src.utils.circuit_breaker import (
        CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError, 
        get_circuit_breaker, CircuitState
    )
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

# 텔레그램 알림 import
try:
    from src.utils.telegram_notifier import TelegramNotifier
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


class LiveTradingEngine:
    """실전 매매 엔진
    
    Circuit Breaker 패턴으로 API 연속 실패 시 자동 중단합니다.
    """
    
    STATE_FILE = "trading_state.json"
    
    def __init__(
        self,
        strategy: BaseStrategy,
        symbols: List[str],
        api_client: KISAPIClient,
        broker=None,
        risk_manager: Optional[RiskManager] = None,
        check_interval: int = 1,
        dry_run: bool = True,
        market: str = "KR",
        allow_extended_hours: bool = False,
        circuit_breaker_config: Optional['CircuitBreakerConfig'] = None,
        enable_telegram: bool = True
    ):
        """초기화
        
        Args:
            strategy: 매매 전략
            symbols: 감시 종목 리스트
            api_client: API 클라이언트
            risk_manager: 리스크 관리자
            check_interval: 감시 주기 (초)
            market: 시장 코드 ("KR" 또는 "US")
            allow_extended_hours: 프리/애프터마켓 거래 허용 여부
            circuit_breaker_config: Circuit Breaker 설정
            enable_telegram: 텔레그램 알림 활성화 여부
        """
        self.strategy = strategy
        self.symbols = symbols
        self.api_client = api_client
        self.broker = broker
        self.risk_manager = risk_manager or RiskManager()
        self.check_interval = check_interval
        self.dry_run = dry_run
        self.market = market
        self.allow_extended_hours = allow_extended_hours
        self.is_running = False
        from src.utils.logger import get_logger
        self.logger = get_logger("LiveTrading")
        
        # 시장 시간 체커 초기화
        if MARKET_HOURS_AVAILABLE:
            self.market_checker = get_market_checker(market)
            self.logger.info(f"시장 시간 체커 초기화: {market}")
        else:
            self.market_checker = None
            self.logger.warning("시장 시간 체커 사용 불가")
        
        # Circuit Breaker 초기화
        self._init_circuit_breaker(circuit_breaker_config)
        
        # 텔레그램 알림 초기화
        self.telegram = None
        if enable_telegram and TELEGRAM_AVAILABLE:
            try:
                self.telegram = TelegramNotifier()
                self.logger.info("텔레그램 알림 초기화 완료")
            except Exception as e:
                self.logger.warning(f"텔레그램 초기화 실패: {e}")
        
        # 상태 로드
        self._load_state()
    
    def _init_circuit_breaker(self, config: Optional['CircuitBreakerConfig'] = None):
        """Circuit Breaker 초기화"""
        if not CIRCUIT_BREAKER_AVAILABLE:
            self.circuit_breaker = None
            self.logger.warning("Circuit Breaker 사용 불가")
            return
        
        # 기본 설정
        if config is None:
            config = CircuitBreakerConfig(
                failure_threshold=5,      # 5회 연속 실패 시 서킷 열림
                success_threshold=2,      # 2회 성공 시 서킷 닫힘
                timeout_seconds=300,      # 5분 대기 후 재시도
                half_open_max_calls=3
            )
        
        self.circuit_breaker = get_circuit_breaker(
            name=f"live_trading_{self.market}",
            config=config,
            on_state_change=self._on_circuit_state_change,
            on_failure=self._on_api_failure
        )
        self.logger.info(f"Circuit Breaker 초기화: {self.circuit_breaker.name}")
    
    def _on_circuit_state_change(self, old_state: str, new_state: str):
        """서킷 상태 변경 콜백"""
        message = f"🔌 서킷 상태 변경: {old_state} → {new_state}"
        self.logger.warning(message)
        
        if new_state == "open":
            message = f"🚨 거래 중단! API 연속 실패로 서킷 열림 (5분 후 재시도)"
            self._send_telegram_alert(message, level="error")
        elif new_state == "closed":
            message = "✅ 거래 재개! 서킷 복구 완료"
            self._send_telegram_alert(message, level="info")
    
    def _on_api_failure(self, exception: Exception):
        """API 실패 콜백"""
        self.logger.error(f"API 호출 실패: {exception}")
        
        if self.circuit_breaker:
            stats = self.circuit_breaker.stats
            if stats.consecutive_failures >= 3:
                self._send_telegram_alert(
                    f"⚠️ API 연속 실패 {stats.consecutive_failures}회 - 주의 필요",
                    level="warning"
                )
    
    def _send_telegram_alert(self, message: str, level: str = "info"):
        """텔레그램 알림 전송"""
        if self.telegram:
            try:
                self.telegram.send_message(f"[{self.market}] {message}")
            except Exception as e:
                self.logger.error(f"텔레그램 전송 실패: {e}")
    
    def _load_state(self):
        """상태 로드"""
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, 'r') as f:
                    self._state = json.load(f)
                self.logger.info("이전 상태 로드 완료")
            else:
                self._state = {'positions': {}, 'last_signals': {}}
        except Exception as e:
            self.logger.error(f"상태 로드 실패: {e}")
            self._state = {'positions': {}, 'last_signals': {}}
    
    def _save_state(self):
        """상태 저장"""
        try:
            self._state['last_updated'] = datetime.now().isoformat()
            with open(self.STATE_FILE, 'w') as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            self.logger.error(f"상태 저장 실패: {e}")
    
    def get_circuit_status(self) -> Dict[str, Any]:
        """서킷 브레이커 상태 조회"""
        if self.circuit_breaker:
            return self.circuit_breaker.get_status()
        return {'state': 'unavailable'}
        
    def start(self):
        """매매 시작"""
        self.is_running = True
        self.logger.info("실전 매매 시작")
        self._send_telegram_alert("🚀 자동매매 시작", level="info")
        
        try:
            while self.is_running:
                self._process_cycle()
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            self.logger.error(f"치명적 오류: {e}")
            self._send_telegram_alert(f"💀 치명적 오류로 매매 중단: {e}", level="error")
            self.stop()
            
    def stop(self):
        """매매 종료"""
        self.is_running = False
        self._save_state()
        self.logger.info("실전 매매 종료")
        self._send_telegram_alert("🛑 자동매매 종료", level="info")
        
    def _process_cycle(self):
        """매매 주기 처리"""
        # Circuit Breaker 체크
        if self.circuit_breaker and self.circuit_breaker.state == CircuitState.OPEN:
            remaining = self.circuit_breaker._get_remaining_timeout()
            if datetime.now().second < self.check_interval:  # 1분마다 로그
                self.logger.info(f"서킷 열림 - {remaining:.0f}초 후 재시도")
            return
        
        # 시장 운영 시간 체크
        if self.market_checker:
            if not self.market_checker.is_market_open(allow_extended=self.allow_extended_hours):
                if datetime.now().minute % 5 == 0 and datetime.now().second < self.check_interval:
                    status = self.market_checker.get_status_message()
                    self.logger.info(f"거래 대기 중: {status}")
                return
        
        for symbol in self.symbols:
            try:
                self._process_symbol(symbol)
            except CircuitBreakerError as e:
                self.logger.warning(f"서킷 열림으로 {symbol} 스킵: {e}")
                break  # 서킷 열리면 모든 종목 스킵
            except Exception as e:
                self.logger.error(f"Error processing {symbol}: {e}")
                if self.circuit_breaker:
                    self.circuit_breaker._handle_failure(e)
    
    def _process_symbol(self, symbol: str):
        """종목별 처리 (Circuit Breaker 적용)"""
        # Circuit Breaker로 API 호출 래핑
        if self.circuit_breaker:
            df = self.circuit_breaker.call(
                self._fetch_price_data, symbol
            )
        else:
            df = self._fetch_price_data(symbol)
        
        if df is None or df.empty:
            return
        
        # 신호 생성
        signals = self.strategy.generate_signals(df)
        current_signal = signals['signal'].iloc[-1]
        
        # 상태 저장
        self._state.setdefault('positions', {})
        self._state.setdefault('last_signals', {})
        self._state['last_signals'][symbol] = {
            'signal': int(current_signal),
            'timestamp': datetime.now().isoformat()
        }
        
        # 주문 실행
        if current_signal == 1:
            self._place_buy_order(symbol)
        elif current_signal == -1:
            self._place_sell_order(symbol)
    
    def _fetch_price_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """가격 데이터 조회"""
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
        prices = self.api_client.get_daily_price_history(symbol, start_date, end_date)
        if not prices:
            return None
        
        df = pd.DataFrame([vars(p) for p in prices])
        return df if not df.empty else None
                
    def _place_buy_order(self, symbol: str):
        """매수 주문"""
        try:
            if self.circuit_breaker:
                current_price = self.circuit_breaker.call(
                    self.api_client.get_current_price, symbol
                )
                account = self.circuit_breaker.call(
                    self.api_client.get_account_balance
                )
            else:
                current_price = self.api_client.get_current_price(symbol)
                account = self.api_client.get_account_balance()
            
            target_amount = account.cash * 0.1
            quantity = int(target_amount // current_price)
            
            if quantity <= 0:
                return

            exchange = "KR" if self.market == "KR" else "NASD"
            order_price = current_price if self.market == "US" else 0

            order = Order(
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                quantity=quantity,
                price=order_price,
                created_at=datetime.now()
            )
            
            current_pos_value = 0
            if self.risk_manager.check_order(order, current_pos_value):
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] BUY {symbol} {quantity} @ {current_price:,.0f}")
                    return
                if self.circuit_breaker:
                    order_fn = self.broker.place_order if self.broker is not None else self.api_client.place_order
                    self.circuit_breaker.call(order_fn, order, exchange=exchange)
                else:
                    if self.broker is not None:
                        self.broker.place_order(order, exchange=exchange)
                    else:
                        self.api_client.place_order(order, exchange=exchange)
                
                self.logger.info(f"매수 주문 실행: {symbol} {quantity}주")
                self._send_telegram_alert(f"📈 매수: {symbol} {quantity}주 @ {current_price:,.0f}원")
                self._save_state()
                
        except CircuitBreakerError:
            raise
        except Exception as e:
            self.logger.error(f"매수 주문 실패 {symbol}: {e}")
            if self.circuit_breaker:
                self.circuit_breaker._handle_failure(e)
            
    def _place_sell_order(self, symbol: str):
        """매도 주문"""
        try:
            if self.circuit_breaker:
                account = self.circuit_breaker.call(
                    self.api_client.get_account_balance
                )
            else:
                account = self.api_client.get_account_balance()
            
            quantity = 0
            exchange = "KR"
            order_price = 0
            for pos in account.positions:
                if pos.symbol == symbol:
                    quantity = pos.quantity
                    exchange = getattr(pos, "exchange", "KR")
                    order_price = pos.current_price if self.market == "US" else 0
                    break
            
            if quantity > 0:
                order = Order(
                    symbol=symbol,
                    order_type=OrderType.MARKET,
                    side=OrderSide.SELL,
                    quantity=quantity,
                    price=order_price,
                    created_at=datetime.now()
                )

                if self.dry_run:
                    self.logger.info(f"[DRY RUN] SELL {symbol} {quantity}")
                    return

                if self.circuit_breaker:
                    order_fn = self.broker.place_order if self.broker is not None else self.api_client.place_order
                    self.circuit_breaker.call(order_fn, order, exchange=exchange)
                else:
                    if self.broker is not None:
                        self.broker.place_order(order, exchange=exchange)
                    else:
                        self.api_client.place_order(order, exchange=exchange)
                
                self.logger.info(f"매도 주문 실행: {symbol} {quantity}주")
                self._send_telegram_alert(f"📉 매도: {symbol} {quantity}주")
                self._save_state()
                
        except CircuitBreakerError:
            raise
        except Exception as e:
            self.logger.error(f"매도 주문 실패 {symbol}: {e}")
            if self.circuit_breaker:
                self.circuit_breaker._handle_failure(e)

