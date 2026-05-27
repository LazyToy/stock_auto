"""OHLCV 합성 데이터 팩토리

패턴 탐지기의 경계 조건 검증에 사용할 합성 OHLCV DataFrame을 생성합니다.
실제 API 호출 없이 재현 가능한 테스트 데이터를 제공하는 것이 목적입니다.
"""

import pandas as pd


def make_ohlcv(
    n: int = 20,
    start: str = "2024-01-02",
    base_price: float = 100.0,
    step: float = 1.0,
    volume: int = 10_000,
    freq: str = "1D",
    columns_uppercase: bool = False,
    body_pct: float = 0.005,
    wick_pct: float = 0.010,
) -> pd.DataFrame:
    """합성 OHLCV DataFrame을 생성합니다.

    open/high/low는 각 캔들의 close 가격 대비 비율(body_pct, wick_pct)로 계산합니다.
    step > 0이면 양봉(open < close), step < 0이면 음봉(open > close)이 됩니다.

    Args:
        n: 캔들 수
        start: 시작 날짜 문자열 (YYYY-MM-DD)
        base_price: 첫 번째 캔들의 종가
        step: 캔들당 종가 변화량 (양수=상승 추세, 음수=하락 추세)
        volume: 거래량 (고정)
        freq: 시간 주기 (예: "1D", "5min", "1h")
        columns_uppercase: True이면 Open/High/Low/Close/Volume 대문자 컬럼 반환
        body_pct: 캔들 몸통 크기 비율 (close 대비). open = close ∓ close*body_pct
        wick_pct: 캔들 전체 범위 비율 (close 대비). high/low = close ± close*wick_pct
                  반드시 body_pct < wick_pct 이어야 유효한 캔들이 된다.

    Returns:
        DatetimeIndex를 인덱스로 갖는 OHLCV DataFrame

    Examples:
        >>> # 10개 양봉 (상승 추세)
        >>> make_ohlcv(n=10, step=1.0)
        >>> # 10개 음봉 (하락 추세)
        >>> make_ohlcv(n=10, step=-1.0)
        >>> # 대문자 컬럼 (정규화 테스트용)
        >>> make_ohlcv(n=5, columns_uppercase=True)
    """
    if body_pct >= wick_pct:
        raise ValueError(
            f"body_pct({body_pct})는 wick_pct({wick_pct})보다 작아야 유효한 캔들이 생성됩니다."
        )

    dates = pd.date_range(start=start, periods=n, freq=freq)
    closes = [base_price + i * step for i in range(n)]

    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []

    for c in closes:
        body = c * body_pct
        wick = c * wick_pct
        if step >= 0:
            # 양봉: open < close, high는 close 위, low는 open 아래
            o = c - body
            h = c + wick
            lo = o - wick
        else:
            # 음봉: open > close, high는 open 위, low는 close 아래
            o = c + body
            h = o + wick
            lo = c - wick
        opens.append(o)
        highs.append(h)
        lows.append(lo)

    col_map = (
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": [volume] * n}
        if columns_uppercase
        else {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [volume] * n}
    )
    return pd.DataFrame(col_map, index=dates)


def make_ohlcv_with_duplicate_timestamps(
    n: int = 5,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """중복 timestamp가 포함된 합성 OHLCV DataFrame을 생성합니다.

    마지막 행의 timestamp를 첫 번째 행과 동일하게 만들어 중복을 유발합니다.
    """
    df = make_ohlcv(n=n, start=start)
    # 마지막 행 timestamp를 첫 번째와 동일하게 설정
    new_index = df.index.tolist()
    new_index[-1] = new_index[0]
    df.index = pd.DatetimeIndex(new_index)
    return df


def make_ohlcv_reversed(
    n: int = 10,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """날짜 역순 정렬 합성 OHLCV DataFrame을 생성합니다."""
    df = make_ohlcv(n=n, start=start)
    return df.iloc[::-1]


def make_ohlcv_with_invalid_row(
    n: int = 10,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """비정상 high/low가 포함된 합성 OHLCV DataFrame을 생성합니다.

    마지막 행에서 high < close인 상태를 만들어 유효성 검증을 테스트합니다.
    """
    df = make_ohlcv(n=n, start=start)
    # high 값을 close보다 낮게 설정하여 비정상 상태 유발
    df.iloc[-1, df.columns.get_loc("high")] = df.iloc[-1]["close"] - 2.0
    return df


def make_kis_kr_minute_response(
    n: int = 5,
) -> dict:
    """KIS KR 분봉 API 응답 형식의 픽스처 딕셔너리를 생성합니다.

    실제 API 호출 없이 파서 검증에 사용합니다.
    """
    items = []
    base_hour = 90000  # 09:00:00 (HHMMSS 형식)
    for i in range(n):
        hour_str = f"{base_hour + i * 100:06d}"
        items.append(
            {
                "stck_cntg_hour": hour_str,
                "stck_oprc": str(10000 + i * 10),
                "stck_hgpr": str(10010 + i * 10),
                "stck_lwpr": str(9990 + i * 10),
                "stck_prpr": str(10005 + i * 10),
                "cntg_vol": str(500 + i * 50),
            }
        )
    return {"output2": items}


def make_kis_us_minute_response(
    n: int = 5,
    date_str: str = "20240102",
) -> dict:
    """KIS US 분봉 API 응답 형식의 픽스처 딕셔너리를 생성합니다.

    실제 API 호출 없이 파서 검증에 사용합니다.
    """
    items = []
    base_hour = 93000  # 09:30:00 (HHMMSS 형식)
    for i in range(n):
        hour_str = f"{base_hour + i * 100:06d}"
        items.append(
            {
                "xymd": date_str,
                "xhms": hour_str,
                "open": str(150.0 + i * 0.5),
                "high": str(151.0 + i * 0.5),
                "low": str(149.5 + i * 0.5),
                "last": str(150.5 + i * 0.5),
                "evol": str(1000 + i * 100),
            }
        )
    return {"output2": items}
