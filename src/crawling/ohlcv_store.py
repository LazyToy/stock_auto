"""
이슈 #12: SQLite OHLCV 이력 저장소.
20일 거래량 평균(RVOL 계산용) 등 이력 집계를 위한 로컬 캐시.
stdlib sqlite3 만 사용 — 외부 의존성 없음.
DB 파일 기본 경로: {repo_root}/data/ohlcv.db (repo 내부, .gitignore 필요)
"""
from __future__ import annotations

import os
import sqlite3

_300MB = 300 * 1024 * 1024

_DDL = """
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    ticker  TEXT    NOT NULL,
    date    TEXT    NOT NULL,
    open    REAL    NOT NULL DEFAULT 0,
    high    REAL    NOT NULL DEFAULT 0,
    low     REAL    NOT NULL DEFAULT 0,
    close   REAL    NOT NULL DEFAULT 0,
    volume  REAL    NOT NULL DEFAULT 0,
    amount  REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_date ON daily_ohlcv (ticker, date DESC);
"""


class OHLCVStore:
    """일별 OHLCV 이력을 SQLite 에 저장·조회하는 저장소."""

    def __init__(self, db_path: str = "data/ohlcv.db") -> None:
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.executescript(_DDL)
        self._con.commit()

    # ------------------------------------------------------------------
    # 쓰기
    # ------------------------------------------------------------------
    def upsert(
        self,
        ticker: str,
        date: str,
        *,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        amount: float,
        normalize_kr: bool = False,
        normalize_us: bool = False,
    ) -> None:
        """(ticker, date) 기준 INSERT OR REPLACE (upsert)."""
        if normalize_kr:
            ticker = str(ticker).zfill(6)
        if normalize_us:
            ticker = str(ticker).upper()

        self._con.execute(
            """
            INSERT OR REPLACE INTO daily_ohlcv
                (ticker, date, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, date, open_, high, low, close, volume, amount),
        )
        self._con.commit()

    def upsert_many(self, rows: list[tuple]) -> None:
        """대량 upsert: rows = [(ticker, date, open_, high, low, close, volume, amount), ...]"""
        self._con.executemany(
            """
            INSERT OR REPLACE INTO daily_ohlcv
                (ticker, date, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._con.commit()

    # ------------------------------------------------------------------
    # 읽기
    # ------------------------------------------------------------------
    def avg_volume(self, ticker: str, window: int = 20) -> float:
        """최근 window 거래일의 평균 거래량. 데이터 없으면 0.0."""
        row = self._con.execute(
            """
            SELECT AVG(volume)
            FROM (
                SELECT volume
                FROM daily_ohlcv
                WHERE ticker = ?
                ORDER BY date DESC
                LIMIT ?
            )
            """,
            (ticker, window),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    def latest_dates(self, ticker: str, n: int = 20) -> list[str]:
        """최근 n개 거래일 목록 (내림차순)."""
        rows = self._con.execute(
            "SELECT date FROM daily_ohlcv WHERE ticker=? ORDER BY date DESC LIMIT ?",
            (ticker, n),
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # 유지보수
    # ------------------------------------------------------------------
    def _db_size_bytes(self) -> int:
        """DB 파일 크기(바이트). :memory: 는 0 반환."""
        if self._db_path == ":memory:":
            return 0
        try:
            return os.path.getsize(self._db_path)
        except OSError:
            return 0

    def check_size_warning(self) -> None:
        """DB 파일이 300MB 초과 시 경고 로그 출력."""
        size = self._db_size_bytes()
        if size >= _300MB:
            mb = size / (1024 * 1024)
            print(f"[경고] OHLCV DB 크기 {mb:.1f}MB - 300MB 이상. 오래된 이력 정리를 권장합니다.")

    def close(self) -> None:
        self._con.close()


def compute_avg_volume(ticker: str, window: int = 20, db_path: str = "data/ohlcv.db") -> float:
    """모듈 수준 편의 함수: 기본(또는 지정) DB 경로에서 ticker의 window일 평균 거래량 반환."""
    store = OHLCVStore(db_path)
    try:
        return store.avg_volume(ticker, window)
    finally:
        store.close()
