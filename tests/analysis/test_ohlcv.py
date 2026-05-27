"""PR-01: OHLCV 계약 테스트

normalize_ohlcv_frame, stock_prices_to_ohlcv, validate_ohlcv_frame,
ensure_datetime_index 함수와 KIS 분봉 파서 보정을 검증합니다.

실제 API 호출은 하지 않으며, 합성 픽스처와 unittest.mock만 사용합니다.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from tests.fixtures.ohlcv_factory import (
    make_kis_kr_minute_response,
    make_kis_us_minute_response,
    make_ohlcv,
    make_ohlcv_reversed,
    make_ohlcv_with_duplicate_timestamps,
    make_ohlcv_with_invalid_row,
)

# ────────────────────────────────────────────────────────────
# normalize_ohlcv_frame 테스트
# ────────────────────────────────────────────────────────────


class TestNormalizeOhlcvFrame(unittest.TestCase):
    """normalize_ohlcv_frame 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.ohlcv import normalize_ohlcv_frame

        self.fn = normalize_ohlcv_frame

    def test_대문자_컬럼이_소문자로_변환된다(self) -> None:
        """Open/High/Low/Close/Volume → open/high/low/close/volume"""
        df_upper = make_ohlcv(n=5, columns_uppercase=True)
        result = self.fn(df_upper)
        self.assertIn("open", result.columns)
        self.assertIn("high", result.columns)
        self.assertIn("low", result.columns)
        self.assertIn("close", result.columns)
        self.assertIn("volume", result.columns)
        self.assertNotIn("Open", result.columns)

    def test_소문자_컬럼은_그대로_유지된다(self) -> None:
        """이미 소문자 컬럼은 변환 없이 통과한다"""
        df = make_ohlcv(n=5)
        result = self.fn(df)
        self.assertIn("close", result.columns)

    def test_날짜_역순_데이터가_오름차순으로_정렬된다(self) -> None:
        """역순 정렬 데이터는 오름차순으로 재정렬된다"""
        df_reversed = make_ohlcv_reversed(n=10)
        result = self.fn(df_reversed)
        self.assertTrue(result.index.is_monotonic_increasing)

    def test_중복_timestamp가_마지막_값으로_제거된다(self) -> None:
        """중복 timestamp는 마지막 행의 값을 남기고 제거된다"""
        df = make_ohlcv(n=5)
        # 첫 번째 행의 timestamp를 복제 → 중복 생성 (마지막 값을 의도적으로 변경)
        sentinel_close = 99999.0
        new_index = df.index.tolist()
        new_index[-1] = new_index[0]  # 마지막 행 timestamp = 첫 번째 행 timestamp
        df = df.copy()
        df.iloc[-1, df.columns.get_loc("close")] = sentinel_close
        df.index = pd.DatetimeIndex(new_index)

        result = self.fn(df)

        # 중복이 제거되었는가
        self.assertEqual(result.index.duplicated().sum(), 0)
        # keep="last" 이므로 sentinel_close 값이 남아야 한다
        self.assertEqual(result.loc[result.index[0], "close"], sentinel_close)

    def test_DatetimeIndex가_보장된다(self) -> None:
        """결과 DataFrame의 인덱스는 DatetimeIndex여야 한다"""
        df = make_ohlcv(n=5)
        result = self.fn(df)
        self.assertIsInstance(result.index, pd.DatetimeIndex)

    def test_None_입력은_ValueError를_발생시킨다(self) -> None:
        """None을 전달하면 ValueError가 발생한다"""
        with self.assertRaises(ValueError):
            self.fn(None)


# ────────────────────────────────────────────────────────────
# validate_ohlcv_frame 테스트
# ────────────────────────────────────────────────────────────


class TestValidateOhlcvFrame(unittest.TestCase):
    """validate_ohlcv_frame 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.ohlcv import validate_ohlcv_frame

        self.fn = validate_ohlcv_frame

    def test_정상_데이터는_유효하다(self) -> None:
        """정상적인 OHLCV DataFrame은 True와 빈 에러 리스트를 반환한다"""
        df = make_ohlcv(n=10)
        is_valid, errors = self.fn(df)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_빈_DataFrame은_유효하지_않다(self) -> None:
        """빈 DataFrame은 유효하지 않다 — dtype이 numeric이어도 insufficient_data를 반환한다"""
        # 빈 DataFrame이지만 numeric dtype + DatetimeIndex를 명시
        dates = pd.DatetimeIndex([])
        df = pd.DataFrame(index=dates).assign(
            open=pd.Series(dtype=float),
            high=pd.Series(dtype=float),
            low=pd.Series(dtype=float),
            close=pd.Series(dtype=float),
            volume=pd.Series(dtype=int),
        )
        is_valid, errors = self.fn(df)
        self.assertFalse(is_valid)
        self.assertTrue(any("insufficient_data" in e for e in errors))

    def test_min_rows_미달시_insufficient_data(self) -> None:
        """min_rows보다 행이 적으면 insufficient_data 에러가 반환된다"""
        df = make_ohlcv(n=3)
        is_valid, errors = self.fn(df, min_rows=5)
        self.assertFalse(is_valid)
        self.assertTrue(any("insufficient_data" in e for e in errors))

    def test_비정상_high_low_행이_검출된다(self) -> None:
        """high < close인 비정상 행이 존재하면 invalid_candle 에러가 포함된다"""
        df = make_ohlcv_with_invalid_row(n=10)
        is_valid, errors = self.fn(df)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid_candle" in e for e in errors))

    def test_필수_컬럼_누락시_에러(self) -> None:
        """필수 컬럼이 없으면 missing_columns 에러가 반환된다"""
        df = pd.DataFrame({"open": [100.0], "close": [101.0]})
        is_valid, errors = self.fn(df)
        self.assertFalse(is_valid)
        self.assertTrue(any("missing_columns" in e for e in errors))

    def test_None_입력은_invalid_input_none_반환한다(self) -> None:
        """None 입력은 크래시 없이 (False, ['invalid_input:none'])을 반환한다"""
        is_valid, errors = self.fn(None)
        self.assertFalse(is_valid)
        self.assertIn("invalid_input:none", errors)

    def test_min_rows_0이하면_invalid_min_rows_반환한다(self) -> None:
        """min_rows <= 0이면 invalid_min_rows 에러가 반환된다"""
        df = make_ohlcv(n=5)
        is_valid, errors = self.fn(df, min_rows=0)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid_min_rows" in e for e in errors))

    def test_RangeIndex_DataFrame은_invalid_datetime_index_반환한다(self) -> None:
        """DatetimeIndex도 datetime 컬럼도 없는 DataFrame은 invalid_datetime_index 에러를 반환한다"""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [102.0],
                "low": [99.0],
                "close": [101.0],
                "volume": [1000],
            }
        )
        is_valid, errors = self.fn(df)
        self.assertFalse(is_valid)
        self.assertIn("invalid_datetime_index", errors)

    def test_문자열_OHLCV_컬럼은_invalid_dtype_반환한다(self) -> None:
        """numeric이 아닌 OHLCV 컬럼은 invalid_dtype 에러가 반환된다"""
        dates = pd.date_range("2024-01-02", periods=2, freq="1D")
        df = pd.DataFrame(
            {
                "open": ["100.0", "101.0"],  # 문자열
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.0],
                "volume": [1000, 1100],
            },
            index=dates,
        )
        is_valid, errors = self.fn(df)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid_dtype:open" in e for e in errors))

    def test_파싱_불가_datetime_컬럼은_invalid_datetime_column_반환한다(self) -> None:
        """datetime 컬럼 값이 파싱 불가이면 invalid_datetime_column reason이 반환된다"""
        df = pd.DataFrame(
            {
                "datetime": ["bad-date"],
                "open": [1.0],
                "high": [2.0],
                "low": [0.5],
                "close": [1.5],
                "volume": [100],
            }
        )
        is_valid, errors = self.fn(df)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid_datetime_column" in e for e in errors))

    def test_유효한_datetime_컬럼은_정상_통과한다(self) -> None:
        """파싱 가능한 datetime 컬럼 + 정상 OHLCV 데이터는 valid로 통과한다"""
        df = pd.DataFrame(
            {
                "datetime": ["2024-01-02"],
                "open": [100.0],
                "high": [102.0],
                "low": [99.0],
                "close": [101.0],
                "volume": [1000],
            }
        )
        is_valid, errors = self.fn(df)
        self.assertTrue(is_valid, f"예상치 못한 에러: {errors}")


# ────────────────────────────────────────────────────────────
# ensure_datetime_index 테스트
# ────────────────────────────────────────────────────────────


class TestEnsureDatetimeIndex(unittest.TestCase):
    """ensure_datetime_index 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.ohlcv import ensure_datetime_index

        self.fn = ensure_datetime_index

    def test_datetime_컬럼을_인덱스로_승격한다(self) -> None:
        """'datetime' 컬럼이 있으면 DatetimeIndex로 설정한다"""
        df = make_ohlcv(n=5)
        df = df.reset_index().rename(columns={"index": "datetime"})
        result = self.fn(df)
        self.assertIsInstance(result.index, pd.DatetimeIndex)
        self.assertNotIn("datetime", result.columns)

    def test_이미_DatetimeIndex이면_그대로_반환한다(self) -> None:
        """이미 DatetimeIndex인 경우 변환 없이 반환한다"""
        df = make_ohlcv(n=5)
        result = self.fn(df)
        self.assertIsInstance(result.index, pd.DatetimeIndex)

    def test_정수_인덱스_DataFrame에_datetime_컬럼_없으면_ValueError(self) -> None:
        """DatetimeIndex도 datetime 컬럼도 없는 경우 ValueError를 발생시킨다"""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "close": [101.0],
                "high": [102.0],
                "low": [99.0],
                "volume": [1000],
            }
        )
        with self.assertRaises(ValueError):
            self.fn(df)

    def test_None_입력은_ValueError를_발생시킨다(self) -> None:
        """None을 전달하면 ValueError가 발생한다"""
        with self.assertRaises(ValueError):
            self.fn(None)


# ────────────────────────────────────────────────────────────
# stock_prices_to_ohlcv 테스트
# ────────────────────────────────────────────────────────────


class TestStockPricesToOhlcv(unittest.TestCase):
    """stock_prices_to_ohlcv 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.ohlcv import stock_prices_to_ohlcv
        from src.data.models import StockPrice

        self.fn = stock_prices_to_ohlcv
        self.StockPrice = StockPrice

    def _make_prices(self, n: int = 5, symbol: str = "005930") -> list:
        """테스트용 StockPrice 리스트 생성"""
        return [
            self.StockPrice(
                symbol=symbol,
                datetime=datetime(2024, 1, 2, 9, i, 0),
                open=10000.0 + i * 10,
                high=10010.0 + i * 10,
                low=9990.0 + i * 10,
                close=10005.0 + i * 10,
                volume=1000 + i * 100,
            )
            for i in range(n)
        ]

    def test_StockPrice_리스트가_OHLCV_DataFrame으로_변환된다(self) -> None:
        """StockPrice 리스트가 올바른 OHLCV DataFrame으로 변환된다"""
        prices = self._make_prices(n=5)
        result = self.fn(prices)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 5)
        for col in ("open", "high", "low", "close", "volume"):
            self.assertIn(col, result.columns)

    def test_빈_리스트는_빈_DataFrame을_반환한다(self) -> None:
        """빈 리스트를 넣으면 빈 DataFrame이 반환된다"""
        result = self.fn([])
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 0)

    def test_결과_DataFrame의_인덱스가_DatetimeIndex다(self) -> None:
        """변환된 DataFrame의 인덱스는 DatetimeIndex여야 한다"""
        prices = self._make_prices(n=5)
        result = self.fn(prices)
        self.assertIsInstance(result.index, pd.DatetimeIndex)

    def test_결과가_시간_오름차순으로_정렬된다(self) -> None:
        """역순으로 정렬된 StockPrice도 오름차순 DataFrame으로 변환된다"""
        prices = self._make_prices(n=5)
        prices_reversed = list(reversed(prices))
        result = self.fn(prices_reversed)
        self.assertTrue(result.index.is_monotonic_increasing)

    def test_None_입력은_ValueError를_발생시킨다(self) -> None:
        """None 전달은 빈 리스트와 달리 ValueError가 발생한다"""
        with self.assertRaises(ValueError):
            self.fn(None)

    def test_빈_리스트_결과는_DatetimeIndex와_numeric_dtype을_갖는다(self) -> None:
        """빈 리스트 변환 결과는 DatetimeIndex + numeric dtype — validate_ohlcv_frame 호환 조건"""
        result = self.fn([])
        # 인덱스 타입
        self.assertIsInstance(result.index, pd.DatetimeIndex)
        # OHLCV 컬럼 numeric dtype
        for col in ("open", "high", "low", "close", "volume"):
            self.assertIn(col, result.columns)
            self.assertTrue(
                pd.api.types.is_numeric_dtype(result[col]),
                f"{col} 컬럼이 numeric dtype이 아닙니다: {result[col].dtype}",
            )

    def test_빈_리스트_결과는_validate_ohlcv_frame에서_insufficient_data만_반환한다(self) -> None:
        """빈 리스트 변환 결과를 validate에 넣으면 insufficient_data 외 에러가 없어야 한다"""
        from src.analysis.ohlcv import validate_ohlcv_frame

        result = self.fn([])
        is_valid, errors = validate_ohlcv_frame(result)
        self.assertFalse(is_valid)  # 행이 0개이므로 invalid
        # 오직 insufficient_data 에러만 있어야 한다 (dtype/datetime 에러 없음)
        non_data_errors = [e for e in errors if "insufficient_data" not in e]
        self.assertEqual(
            non_data_errors,
            [],
            f"예상치 못한 에러 발생: {non_data_errors}",
        )


# ────────────────────────────────────────────────────────────
# KIS 분봉 파서 보정 테스트 (monkeypatch 방식)
# ────────────────────────────────────────────────────────────


class TestKisMinutePriceParser(unittest.TestCase):
    """KISAPIClient.get_minute_price를 monkeypatch로 직접 호출하여 파서를 검증합니다.

    _ensure_token과 _make_request를 mock하여 실제 API 호출 없이
    프로덕션 파서 로직(symbol/datetime 필드 포함 여부)을 검증합니다.
    """

    def _make_client(self, market: str = "KR"):
        """테스트용 KISAPIClient 인스턴스를 생성합니다 (인증 없음)."""
        from src.data.api_client import KISAPIClient

        client = KISAPIClient.__new__(KISAPIClient)
        client.market = market
        client.access_token = "test_token"
        client.app_key = "test_key"
        client.app_secret = "test_secret"
        client.max_retries = 1
        # __init__에서 Config에 의존하는 base_url을 직접 설정
        client.base_url = "https://mock.api"
        client.token_expires_at = None
        # rate_limiter mock
        client.rate_limiter = MagicMock()
        client.rate_limiter.wait = MagicMock()
        return client

    def test_KR_분봉_파서가_symbol과_datetime을_포함한다(self) -> None:
        """KISAPIClient.get_minute_price KR 경로가 StockPrice에 symbol/datetime을 채운다"""
        from src.data.api_client import KISAPIClient

        client = self._make_client(market="KR")
        response = make_kis_kr_minute_response(n=5)

        with (
            patch.object(client, "_ensure_token"),
            patch.object(client, "_make_request", return_value=response),
        ):
            prices = client.get_minute_price(symbol="005930", interval=1, count=5)

        self.assertEqual(len(prices), 5)
        for p in prices:
            self.assertEqual(p.symbol, "005930")
            self.assertIsInstance(p.datetime, datetime)

    def test_US_분봉_파서가_symbol과_datetime을_포함한다(self) -> None:
        """KISAPIClient.get_minute_price US 경로가 StockPrice에 symbol/datetime을 채운다"""
        from src.data.api_client import KISAPIClient

        client = self._make_client(market="US")
        response = make_kis_us_minute_response(n=5, date_str="20240102")

        with (
            patch.object(client, "_ensure_token"),
            patch.object(client, "_make_request", return_value=response),
        ):
            prices = client.get_minute_price(symbol="AAPL", interval=5, count=5)

        self.assertEqual(len(prices), 5)
        for p in prices:
            self.assertEqual(p.symbol, "AAPL")
            self.assertIsInstance(p.datetime, datetime)
            self.assertEqual(p.datetime.year, 2024)
            self.assertEqual(p.datetime.month, 1)
            self.assertEqual(p.datetime.day, 2)

    def test_KR_분봉_OHLCV값이_올바르게_파싱된다(self) -> None:
        """KR 분봉 픽스처의 시가/고가/저가/종가/거래량이 올바르게 파싱된다"""
        from src.data.api_client import KISAPIClient

        client = self._make_client(market="KR")
        response = make_kis_kr_minute_response(n=1)

        with (
            patch.object(client, "_ensure_token"),
            patch.object(client, "_make_request", return_value=response),
        ):
            prices = client.get_minute_price(symbol="005930")

        self.assertEqual(len(prices), 1)
        p = prices[0]
        self.assertGreater(p.open, 0)
        self.assertGreater(p.high, 0)
        self.assertGreater(p.low, 0)
        self.assertGreater(p.close, 0)
        self.assertGreater(p.volume, 0)

    def test_파싱_실패시_빈_리스트_반환한다(self) -> None:
        """잘못된 응답 구조에서 파싱 실패는 해당 항목을 건너뛰고 [] 반환한다"""
        from src.data.api_client import KISAPIClient

        client = self._make_client(market="KR")
        bad_response = {"output2": [{"wrong_key": "bad_data"}]}

        with (
            patch.object(client, "_ensure_token"),
            patch.object(client, "_make_request", return_value=bad_response),
        ):
            prices = client.get_minute_price(symbol="005930")

        # 파싱 실패 → 빈 리스트
        self.assertEqual(prices, [])

    def test_ohlcv_factory_import가_성공한다(self) -> None:
        """fixtures 패키지 임포트가 정상적으로 동작한다"""
        from tests.fixtures.ohlcv_factory import make_ohlcv  # noqa: F401

        df = make_ohlcv(n=3)
        self.assertEqual(len(df), 3)


if __name__ == "__main__":
    unittest.main()
