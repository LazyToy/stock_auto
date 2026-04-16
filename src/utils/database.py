"""SQLite 데이터베이스 관리자

거래 내역, 포트폴리오 히스토리, 시스템 로그 등을 저장합니다.

데이터베이스 스키마:
- trades: 거래 내역
- portfolio_history: 일별 포트폴리오 스냅샷
- alerts: 알림 히스토리
"""

import sqlite3
import os
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# 기본 DB 경로
DEFAULT_DB_PATH = "data/trading.db"


@dataclass
class TradeRecord:
    """거래 기록"""
    id: Optional[int] = None
    timestamp: str = ""
    symbol: str = ""
    side: str = ""          # BUY / SELL
    quantity: int = 0
    price: float = 0.0
    amount: float = 0.0     # quantity * price
    reason: str = ""        # 거래 사유
    profit_pct: Optional[float] = None
    market: str = "KR"


@dataclass
class PortfolioSnapshot:
    """포트폴리오 스냅샷"""
    id: Optional[int] = None
    date: str = ""
    total_asset: float = 0.0
    deposit: float = 0.0
    stock_value: float = 0.0
    stock_count: int = 0
    daily_return_pct: float = 0.0
    cumulative_return_pct: float = 0.0
    market: str = "KR"


class DatabaseManager:
    """SQLite 데이터베이스 관리자"""
    
    def __init__(self, db_path: str = None):
        """초기화
        
        Args:
            db_path: 데이터베이스 파일 경로
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # 디렉토리 생성
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        
        # 테이블 생성
        self._init_tables()
        logger.info(f"데이터베이스 초기화 완료: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """DB 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_tables(self):
        """테이블 초기화"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 거래 내역 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    reason TEXT,
                    profit_pct REAL,
                    market TEXT DEFAULT 'KR',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 포트폴리오 히스토리 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    total_asset REAL NOT NULL,
                    deposit REAL NOT NULL,
                    stock_value REAL NOT NULL,
                    stock_count INTEGER NOT NULL,
                    daily_return_pct REAL,
                    cumulative_return_pct REAL,
                    market TEXT DEFAULT 'KR',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, market)
                )
            """)
            
            # 알림 히스토리 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT,
                    sent BOOLEAN DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 인덱스 생성
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_date ON portfolio_history(date)")
    
    # ============================================
    # 거래 내역 관련
    # ============================================
    
    def insert_trade(self, trade: TradeRecord) -> int:
        """거래 기록 삽입"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (timestamp, symbol, side, quantity, price, amount, reason, profit_pct, market)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.timestamp or datetime.now().isoformat(),
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.price,
                trade.amount or (trade.quantity * trade.price),
                trade.reason,
                trade.profit_pct,
                trade.market
            ))
            return cursor.lastrowid
    
    def get_trades(self, symbol: str = None, start_date: str = None, end_date: str = None, limit: int = 100) -> List[Dict]:
        """거래 내역 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_trade_summary(self, market: str = None) -> Dict[str, Any]:
        """거래 요약 통계"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            market_filter = "AND market = ?" if market else ""
            params = [market] if market else []
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                    SUM(CASE WHEN side = 'BUY' THEN amount ELSE 0 END) as total_buy_amount,
                    SUM(CASE WHEN side = 'SELL' THEN amount ELSE 0 END) as total_sell_amount,
                    AVG(CASE WHEN profit_pct IS NOT NULL THEN profit_pct END) as avg_profit_pct
                FROM trades WHERE 1=1 {market_filter}
            """, params)
            
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    # ============================================
    # 포트폴리오 히스토리 관련
    # ============================================
    
    def insert_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> int:
        """포트폴리오 스냅샷 삽입 (일별 Upsert)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO portfolio_history 
                (date, total_asset, deposit, stock_value, stock_count, daily_return_pct, cumulative_return_pct, market)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.date or date.today().isoformat(),
                snapshot.total_asset,
                snapshot.deposit,
                snapshot.stock_value,
                snapshot.stock_count,
                snapshot.daily_return_pct,
                snapshot.cumulative_return_pct,
                snapshot.market
            ))
            return cursor.lastrowid
    
    def get_portfolio_history(self, market: str = None, days: int = 30) -> List[Dict]:
        """포트폴리오 히스토리 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            market_filter = "AND market = ?" if market else ""
            params = [market, days] if market else [days]
            
            cursor.execute(f"""
                SELECT * FROM portfolio_history 
                WHERE 1=1 {market_filter}
                ORDER BY date DESC LIMIT ?
            """, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_latest_portfolio(self, market: str = "KR") -> Optional[Dict]:
        """최신 포트폴리오 스냅샷 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM portfolio_history 
                WHERE market = ?
                ORDER BY date DESC LIMIT 1
            """, (market,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ============================================
    # 알림 히스토리 관련
    # ============================================
    
    def insert_alert(self, level: str, title: str, message: str, sent: bool = True) -> int:
        """알림 기록 삽입"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alerts (timestamp, level, title, message, sent)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                level,
                title,
                message,
                sent
            ))
            return cursor.lastrowid
    
    def get_alerts(self, level: str = None, limit: int = 50) -> List[Dict]:
        """알림 히스토리 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if level:
                cursor.execute("""
                    SELECT * FROM alerts WHERE level = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (level, limit))
            else:
                cursor.execute("""
                    SELECT * FROM alerts
                    ORDER BY timestamp DESC LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ============================================
    # 유틸리티
    # ============================================
    
    def calculate_daily_return(self, market: str = "KR") -> Optional[float]:
        """일일 수익률 계산"""
        history = self.get_portfolio_history(market=market, days=2)
        
        if len(history) >= 2:
            today = history[0]['total_asset']
            yesterday = history[1]['total_asset']
            if yesterday > 0:
                return ((today - yesterday) / yesterday) * 100
        return None
    
    def get_performance_metrics(self, market: str = "KR", days: int = 30) -> Dict[str, Any]:
        """성과 지표 계산"""
        history = self.get_portfolio_history(market=market, days=days)
        
        if not history:
            return {}
        
        returns = [h.get('daily_return_pct', 0) or 0 for h in history]
        
        # 기본 통계
        avg_return = sum(returns) / len(returns) if returns else 0
        max_return = max(returns) if returns else 0
        min_return = min(returns) if returns else 0
        
        # 승률
        win_count = sum(1 for r in returns if r > 0)
        win_rate = (win_count / len(returns) * 100) if returns else 0
        
        return {
            "period_days": len(history),
            "avg_daily_return": avg_return,
            "max_daily_return": max_return,
            "min_daily_return": min_return,
            "win_rate": win_rate,
            "total_return": history[0].get('cumulative_return_pct', 0) if history else 0
        }


# 전역 인스턴스
_db_instance: Optional[DatabaseManager] = None


def get_db() -> DatabaseManager:
    """전역 DatabaseManager 인스턴스 반환"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
