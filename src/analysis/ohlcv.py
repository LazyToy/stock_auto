"""OHLCV 표준 데이터 계약

모든 Smart Money 패턴 탐지기가 공통으로 사용할 OHLCV DataFrame 정규화,
유효성 검증, 변환 함수를 제공합니다.

데이터 출처(KIS, yfinance, fixture)에 무관하게 동일한 DataFrame 계약을 보장합니다.

표준 OHLCV 컬럼:
    open, high, low, close, volume (모두 소문자)
    인덱스: DatetimeIndex (오름차순)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import pandas as pd

if TYPE_CHECKING:
    from src.data.models import StockPrice

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 상수
# ────────────────────────────────────────────────────────────

# 표준 OHLCV 필수 컬럼 목록
REQUIRED_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")

# OHLCV numeric 컬럼 (dtype 검증 대상)
NUMERIC_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")

# 대문자 → 소문자 컬럼 매핑
_COLUMN_RENAME_MAP: dict[str, str] = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Datetime": "datetime",
    "Date": "datetime",
}


# ────────────────────────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────────────────────────


def normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV DataFrame을 표준 형식으로 정규화합니다.

    수행 작업:
        1. 대문자 컬럼을 소문자로 변환 (Open→open, High→high, ...)
        2. DatetimeIndex 보장 (ensure_datetime_index 호출)
        3. 시간 오름차순 정렬
        4. 중복 timestamp 제거 (마지막 값 유지)

    Args:
        df: 정규화할 OHLCV DataFrame

    Returns:
        정규화된 OHLCV DataFrame

    Raises:
        ValueError: df가 None이거나 datetime 컬럼/DatetimeIndex가 없는 경우
    """
    if df is None:
        raise ValueError("DataFrame이 None입니다.")

    result = df.copy()

    # 1. 컬럼 소문자 변환 (매핑에 있는 것만)
    rename_targets = {k: v for k, v in _COLUMN_RENAME_MAP.items() if k in result.columns}
    if rename_targets:
        result = result.rename(columns=rename_targets)

    # 2. DatetimeIndex 보장
    result = ensure_datetime_index(result)

    # 3. 오름차순 정렬
    if not result.index.is_monotonic_increasing:
        result = result.sort_index()

    # 4. 중복 timestamp 제거 (마지막 값 유지)
    if result.index.duplicated().any():
        before = len(result)
        result = result[~result.index.duplicated(keep="last")]
        after = len(result)
        logger.debug("중복 timestamp 제거: %d행 → %d행", before, after)

    return cast(pd.DataFrame, result)


def validate_ohlcv_frame(
    df: pd.DataFrame,
    min_rows: int = 1,
) -> tuple[bool, list[str]]:
    """OHLCV DataFrame의 유효성을 검증합니다.

    Args:
        df: 검증할 OHLCV DataFrame. None이면 invalid_input:none reason 반환.
        min_rows: 최소 행 수. 1 이상이어야 하며 0 이하면 invalid_min_rows reason 반환.

    Returns:
        (is_valid, errors) 튜플
            is_valid: 모든 검증을 통과하면 True
            errors: 실패한 검증의 reason 문자열 리스트
                    - "invalid_input:none"
                    - "invalid_min_rows:<N>"
                    - "missing_columns:<컬럼명 목록>"
                    - "invalid_datetime_index"
                    - "invalid_dtype:<컬럼명>"
                    - "invalid_datetime_column:<reason>"  (datetime 컬럼 값이 파싱 불가인 경우)
                    - "insufficient_data:rows=<N>,min=<M>"
                    - "invalid_candle:<인덱스>"
    """
    errors: list[str] = []

    # 0. None 입력 처리
    if df is None:
        errors.append("invalid_input:none")
        return False, errors

    # 0-1. min_rows 유효성 검사
    if min_rows < 1:
        errors.append(f"invalid_min_rows:{min_rows}")
        return False, errors

    # 1. 필수 컬럼 확인
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"missing_columns:{','.join(missing)}")
        # 컬럼이 없으면 이후 검증 불가
        return False, errors

    # 2. 시간축 검증: DatetimeIndex 또는 datetime 컬럼이 있어야 한다
    has_datetime_index = isinstance(df.index, pd.DatetimeIndex)
    has_datetime_column = "datetime" in df.columns
    if not has_datetime_index and not has_datetime_column:
        errors.append("invalid_datetime_index")
    elif has_datetime_column and not has_datetime_index:
        # datetime 컬럼이 있으면 실제 파싱 가능 여부를 검증
        try:
            pd.to_datetime(df["datetime"])
        except Exception as e:
            errors.append(f"invalid_datetime_column:{e}")

    # 3. numeric dtype 검증
    for col in NUMERIC_COLUMNS:
        if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            errors.append(f"invalid_dtype:{col}")

    # dtype 오류가 있으면 수치 비교 불가 — 이후 검증 생략
    if any(e.startswith("invalid_dtype") for e in errors):
        return False, errors

    # 4. 최소 행 수 확인
    if len(df) < min_rows:
        errors.append(f"insufficient_data:rows={len(df)},min={min_rows}")

    # 5. 비정상 캔들 검출 (high < max(open, close) or low > min(open, close))
    invalid_mask = (df["high"] < df[["open", "close"]].max(axis=1)) | (
        df["low"] > df[["open", "close"]].min(axis=1)
    )
    invalid_indices = df.index[invalid_mask].tolist()
    for idx in invalid_indices:
        errors.append(f"invalid_candle:{idx}")

    is_valid = len(errors) == 0
    return is_valid, errors


def ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame의 인덱스를 DatetimeIndex로 보장합니다.

    처리 순서:
        1. df가 None이면 ValueError 발생
        2. 이미 DatetimeIndex이면 그대로 반환
        3. 'datetime' 컬럼이 있으면 인덱스로 승격
        4. 위 조건 모두 미충족 시 ValueError 발생

    Args:
        df: 변환할 DataFrame

    Returns:
        DatetimeIndex를 가진 DataFrame

    Raises:
        ValueError: df가 None이거나 DatetimeIndex로 변환할 수 없는 경우
    """
    if df is None:
        raise ValueError("DataFrame이 None입니다.")

    if isinstance(df.index, pd.DatetimeIndex):
        return df

    if "datetime" in df.columns:
        result = df.set_index("datetime")
        result.index = pd.to_datetime(result.index)
        return cast(pd.DataFrame, result)

    # DatetimeIndex로 변환 불가
    raise ValueError(
        "DatetimeIndex 또는 'datetime' 컬럼이 없습니다. "
        "normalize_ohlcv_frame()을 먼저 호출하거나 datetime 컬럼을 추가하세요."
    )


def stock_prices_to_ohlcv(prices: list[StockPrice]) -> pd.DataFrame:
    """StockPrice 리스트를 표준 OHLCV DataFrame으로 변환합니다.

    Args:
        prices: StockPrice 인스턴스 리스트. None은 허용하지 않음.

    Returns:
        표준 OHLCV DataFrame (DatetimeIndex, 오름차순)
        빈 리스트가 입력되면 표준 OHLCV 계약을 만족하는 typed 빈 DataFrame 반환
        (DatetimeIndex + float/int dtype 컬럼 — validate_ohlcv_frame 통과 조건 유지)

    Raises:
        ValueError: prices가 None인 경우
    """
    if prices is None:
        raise ValueError("prices가 None입니다. 빈 리스트([])를 전달하면 빈 DataFrame을 반환합니다.")

    if len(prices) == 0:
        # 표준 OHLCV 계약을 만족하는 typed 빈 DataFrame 반환
        # RangeIndex + object dtype 은 validate_ohlcv_frame 에서 실패하므로
        # DatetimeIndex + numeric dtype 으로 생성해야 한다.
        empty_index = pd.DatetimeIndex([], name="datetime")
        return pd.DataFrame(
            {
                "open": pd.Series(dtype=float),
                "high": pd.Series(dtype=float),
                "low": pd.Series(dtype=float),
                "close": pd.Series(dtype=float),
                "volume": pd.Series(dtype=float),
            },
            index=empty_index,
        )

    records = [
        {
            "datetime": p.datetime,
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        }
        for p in prices
    ]

    df = pd.DataFrame(records)
    df = df.set_index("datetime")
    df.index = pd.to_datetime(df.index)

    # 오름차순 정렬
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    # 중복 제거 (마지막 값 유지)
    if df.index.duplicated().any():
        df = df[~df.index.duplicated(keep="last")]

    return cast(pd.DataFrame, df)
