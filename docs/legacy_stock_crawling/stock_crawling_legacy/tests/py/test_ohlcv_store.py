"""
이슈 #12: SQLite OHLCV 이력 저장소 단위 테스트.
:memory: DB 사용 — 네트워크/파일 I/O 없음.
"""
from __future__ import annotations

import io
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 ohlcv_store 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ──────────────────────────────────────────────
# AC-1: 테이블 생성 + PRIMARY KEY 검증
# ──────────────────────────────────────────────
def test_table_created_with_primary_key():
    """daily_ohlcv 테이블이 (ticker, date) PRIMARY KEY 로 생성되는지 확인."""
    from ohlcv_store import OHLCVStore
    import sqlite3

    s = OHLCVStore(":memory:")
    rows = s._con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_ohlcv'"
    ).fetchall()
    assert rows, "daily_ohlcv 테이블이 존재하지 않음"

    # PRIMARY KEY 인덱스 확인
    info = s._con.execute("PRAGMA index_list('daily_ohlcv')").fetchall()
    pk_exists = any("pk" in str(idx).lower() for idx in info)
    # sqlite PRIMARY KEY는 sqlite_autoindex_ 접두사로 생성됨
    assert pk_exists or any("autoindex" in str(idx).lower() for idx in info), \
        f"PRIMARY KEY 인덱스가 없음: {info}"


# ──────────────────────────────────────────────
# AC-2: upsert 동일 키 2회 호출 시 덮어쓰기
# ──────────────────────────────────────────────
def test_upsert_overwrites_on_duplicate_key():
    """동일 (ticker, date) 2회 upsert 시 마지막 값으로 덮어써야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    s.upsert("005930", "20260401", open_=100, high=110, low=90, close=105, volume=1000, amount=100000)
    s.upsert("005930", "20260401", open_=200, high=220, low=180, close=210, volume=2000, amount=200000)

    rows = s._con.execute(
        "SELECT volume FROM daily_ohlcv WHERE ticker='005930' AND date='20260401'"
    ).fetchall()
    assert len(rows) == 1, "중복 행이 존재해서는 안 됨"
    assert rows[0][0] == 2000, f"마지막 값(2000)으로 덮어쓰지 않음: {rows[0][0]}"


# ──────────────────────────────────────────────
# AC-3: avg_volume 이동평균 정확성 (harnes.md Red 테스트)
# ──────────────────────────────────────────────
def test_ohlcv_upsert_and_avg():
    """harnes.md 명시 Red 테스트: 3일 평균이 정확해야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300)]:
        s.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
    assert s.avg_volume("005930", window=3) == 200.0


def test_avg_volume_window_shorter_than_records():
    """window < 전체 레코드 수인 경우 최근 N개만 사용."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300), ("20260404", 400)]:
        s.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
    # 최근 2개(300, 400) 평균 = 350
    assert s.avg_volume("005930", window=2) == 350.0


def test_avg_volume_no_data_returns_zero():
    """데이터가 없는 ticker 의 avg_volume 은 0.0 이어야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    assert s.avg_volume("UNKNOWN", window=20) == 0.0


# ──────────────────────────────────────────────
# AC-4: 300MB 이상 시 경고 로그
# ──────────────────────────────────────────────
def test_size_warning_triggered():
    """DB 크기가 300MB 이상이면 경고 메시지를 출력해야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    # _db_size_bytes 를 stub 해서 300MB+1 반환
    s._db_size_bytes = lambda: 300 * 1024 * 1024 + 1

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        s.check_size_warning()
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "경고" in output or "WARNING" in output.upper(), \
        f"300MB 초과 시 경고가 출력되지 않음: {output!r}"


def test_size_warning_triggered_at_exact_threshold():
    """DB 크기가 정확히 300MB 여도 경고 메시지를 출력해야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    s._db_size_bytes = lambda: 300 * 1024 * 1024

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        s.check_size_warning()
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "경고" in output or "WARNING" in output.upper(), \
        f"300MB 이상 시 경고가 출력되지 않음: {output!r}"
    output.encode("cp949")


def test_size_warning_not_triggered_below_threshold():
    """300MB 미만이면 경고 없이 조용히 반환해야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    s._db_size_bytes = lambda: 100 * 1024 * 1024  # 100MB

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        s.check_size_warning()
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert output.strip() == "", f"임계값 미만인데 출력 발생: {output!r}"


# ──────────────────────────────────────────────
# 경계 조건: ticker 정규화 (KR zfill(6), US 대문자)
# ──────────────────────────────────────────────
def test_kr_ticker_zero_padded():
    """KR 종목코드는 6자리 zero-padding 이 유지되어야 한다."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    s.upsert("5930", "20260401", open_=0, high=0, low=0, close=0, volume=999, amount=0,
             normalize_kr=True)
    rows = s._con.execute(
        "SELECT ticker FROM daily_ohlcv WHERE date='20260401'"
    ).fetchall()
    assert rows[0][0] == "005930", f"zfill(6) 미적용: {rows[0][0]}"


def test_us_ticker_uppercased():
    """US 종목코드는 대문자 정규화."""
    from ohlcv_store import OHLCVStore

    s = OHLCVStore(":memory:")
    s.upsert("aapl", "20260401", open_=0, high=0, low=0, close=0, volume=500, amount=0,
             normalize_us=True)
    rows = s._con.execute(
        "SELECT ticker FROM daily_ohlcv WHERE date='20260401'"
    ).fetchall()
    assert rows[0][0] == "AAPL", f"대문자 정규화 미적용: {rows[0][0]}"


# ──────────────────────────────────────────────
# 모듈 수준 compute_avg_volume (구현 지시 명시 함수명)
# ──────────────────────────────────────────────
def test_compute_avg_volume_module_function():
    """compute_avg_volume 모듈 수준 함수가 존재하고 올바른 값을 반환해야 한다."""
    import tempfile, os
    from ohlcv_store import OHLCVStore, compute_avg_volume  # compute_avg_volume 아직 없음 → Red

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        s = OHLCVStore(db_path)
        for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300)]:
            s.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
        s.close()

        result = compute_avg_volume("005930", window=3, db_path=db_path)
        assert result == 200.0, f"compute_avg_volume 반환값 오류: {result}"


# ──────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────
if __name__ == "__main__":
    test_table_created_with_primary_key()
    test_upsert_overwrites_on_duplicate_key()
    test_ohlcv_upsert_and_avg()
    test_avg_volume_window_shorter_than_records()
    test_avg_volume_no_data_returns_zero()
    test_size_warning_triggered()
    test_size_warning_triggered_at_exact_threshold()
    test_size_warning_not_triggered_below_threshold()
    test_kr_ticker_zero_padded()
    test_us_ticker_uppercased()
    test_compute_avg_volume_module_function()
    print("[PASS] 전체 테스트 통과")
