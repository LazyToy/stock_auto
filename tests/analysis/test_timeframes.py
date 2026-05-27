"""PR-06: 멀티타임프레임 데이터 수집기 테스트.

실제 네트워크 호출 없이 KIS/yfinance 의존성을 test double로 대체해
타임프레임별 성공/실패 계약과 resample 규칙을 검증합니다.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from src.data.models import StockPrice


def _make_prices(
    symbol: str = "005930",
    n: int = 120,
    start: str = "2024-01-02 09:00:00",
    freq: str = "1min",
) -> list[StockPrice]:
    """테스트용 StockPrice 리스트를 생성한다."""
    dates = pd.date_range(start=start, periods=n, freq=freq)
    prices: list[StockPrice] = []
    for i, ts in enumerate(dates):
        close = 100.0 + i
        prices.append(
            StockPrice(
                symbol=symbol,
                datetime=ts.to_pydatetime(),
                open=close - 0.2,
                high=close + 0.8,
                low=close - 0.7,
                close=close,
                volume=100 + i,
            )
        )
    return prices


class FakeKisClient:
    """KIS API client test double."""

    def __init__(self, market: str = "KR") -> None:
        self.market = market
        self.minute_calls: list[dict[str, object]] = []
        self.daily_calls: list[dict[str, object]] = []
        self.minute_results: dict[int, list[StockPrice] | Exception] = {}
        self.daily_result: list[StockPrice] | Exception = []

    def get_minute_price(
        self,
        symbol: str,
        interval: int = 1,
        count: int = 100,
        exchange: str = "NASD",
    ) -> list[StockPrice]:
        """분봉 호출을 기록하고 준비된 결과를 반환한다."""
        self.minute_calls.append(
            {
                "symbol": symbol,
                "interval": interval,
                "count": count,
                "exchange": exchange,
            }
        )
        result = self.minute_results.get(interval, [])
        if isinstance(result, Exception):
            raise result
        return result

    def get_daily_price_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[StockPrice]:
        """일봉 호출을 기록하고 준비된 결과를 반환한다."""
        self.daily_calls.append({"symbol": symbol, "start_date": start_date, "end_date": end_date})
        if isinstance(self.daily_result, Exception):
            raise self.daily_result
        return self.daily_result


class TestResampleOhlcv(unittest.TestCase):
    """OHLCV resample 규칙을 검증한다."""

    def test_resample_ohlcv_applies_standard_aggregation(self) -> None:
        """open 첫 값, high 최대, low 최소, close 마지막 값, volume 합계를 사용한다."""
        from src.analysis.timeframes import resample_ohlcv

        index = pd.date_range("2024-01-02 09:00:00", periods=5, freq="1min")
        df = pd.DataFrame(
            {
                "open": [10, 11, 12, 13, 14],
                "high": [11, 15, 14, 16, 15],
                "low": [9, 10, 8, 12, 13],
                "close": [10.5, 11.5, 12.5, 13.5, 14.5],
                "volume": [1, 2, 3, 4, 5],
            },
            index=index,
        )

        result = resample_ohlcv(df, "5min")

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["open"], 10)
        self.assertEqual(row["high"], 16)
        self.assertEqual(row["low"], 8)
        self.assertEqual(row["close"], 14.5)
        self.assertEqual(row["volume"], 15)

    def test_resample_ohlcv_normalizes_uppercase_columns(self) -> None:
        """대문자 OHLCV 컬럼도 표준 소문자 컬럼으로 정규화한 뒤 resample한다."""
        from src.analysis.timeframes import resample_ohlcv

        index = pd.date_range("2024-01-02", periods=2, freq="1min")
        df = pd.DataFrame(
            {
                "Open": [1.0, 2.0],
                "High": [2.0, 3.0],
                "Low": [0.5, 1.5],
                "Close": [1.5, 2.5],
                "Volume": [10, 20],
            },
            index=index,
        )

        result = resample_ohlcv(df, "5min")

        self.assertEqual(list(result.columns), ["open", "high", "low", "close", "volume"])
        self.assertEqual(result.iloc[0]["volume"], 30)

    def test_resample_ohlcv_empty_rule_raises_value_error(self) -> None:
        """빈 resample rule은 명시적인 ValueError로 거부한다."""
        from src.analysis.timeframes import resample_ohlcv

        index = pd.date_range("2024-01-02", periods=1, freq="1min")
        df = pd.DataFrame(
            {
                "open": [1.0],
                "high": [2.0],
                "low": [0.5],
                "close": [1.5],
                "volume": [10],
            },
            index=index,
        )

        with self.assertRaisesRegex(ValueError, "rule"):
            resample_ohlcv(df, "")


class TestMultiTimeframeFetcherKr(unittest.TestCase):
    """KR 수집 경로를 검증한다."""

    def test_kr_minute_timeframes_are_resampled_from_one_minute_source(self) -> None:
        """KR 5분봉/1시간봉은 interval=1 원천 데이터에서 resample한다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="KR")
        client.minute_results[1] = _make_prices(n=120)
        client.daily_result = _make_prices(n=30, start="2024-01-01", freq="1D")
        fetcher = MultiTimeframeFetcher(api_client_factory=lambda market: client)

        dataset = fetcher.fetch_symbol("005930", market="KR")

        self.assertTrue(dataset.get(Timeframe.MINUTE_5).is_success)
        self.assertTrue(dataset.get(Timeframe.HOUR_1).is_success)
        self.assertTrue(dataset.get(Timeframe.DAY_1).is_success)
        self.assertEqual([call["interval"] for call in client.minute_calls], [1])
        self.assertEqual(len(dataset.get(Timeframe.MINUTE_5).data), 24)
        self.assertEqual(len(dataset.get(Timeframe.HOUR_1).data), 2)
        self.assertEqual(len(client.daily_calls), 1)
        daily_call = client.daily_calls[0]
        self.assertRegex(daily_call["start_date"], r"^\d{8}$")
        self.assertRegex(daily_call["end_date"], r"^\d{8}$")
        start_date = datetime.strptime(str(daily_call["start_date"]), "%Y%m%d")
        end_date = datetime.strptime(str(daily_call["end_date"]), "%Y%m%d")
        self.assertLess(start_date, end_date)

    def test_kr_intraday_failure_marks_both_intraday_timeframes(self) -> None:
        """KR 1분 원천 수집 실패는 5분/1시간 timeframe error로 기록된다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="KR")
        client.minute_results[1] = RuntimeError("분봉 실패")
        client.daily_result = _make_prices(n=10, start="2024-01-01", freq="1D")
        fetcher = MultiTimeframeFetcher(api_client_factory=lambda market: client)

        dataset = fetcher.fetch_symbol("005930", market="KR")

        self.assertFalse(dataset.get(Timeframe.MINUTE_5).is_success)
        self.assertFalse(dataset.get(Timeframe.HOUR_1).is_success)
        self.assertIn("분봉 실패", dataset.get(Timeframe.MINUTE_5).error)
        self.assertTrue(dataset.get(Timeframe.DAY_1).is_success)


class TestMultiTimeframeFetcherUs(unittest.TestCase):
    """US 수집 경로를 검증한다."""

    def test_us_fetch_uses_minute_api_and_yfinance_daily_fallback(self) -> None:
        """US 5분/1시간은 KIS 분봉, 일봉은 yfinance fallback을 사용한다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="US")
        client.minute_results[5] = _make_prices("AAPL", n=20, freq="5min")
        client.minute_results[60] = _make_prices("AAPL", n=5, freq="60min")
        daily_df = pd.DataFrame(
            {
                "Open": [180.0, 181.0],
                "High": [182.0, 183.0],
                "Low": [179.0, 180.0],
                "Close": [181.5, 182.5],
                "Volume": [1000, 1100],
            },
            index=pd.date_range("2024-01-02", periods=2, freq="1D"),
        )
        yfinance_calls: list[dict[str, str]] = []

        def fetch_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
            """yfinance ?몄텧 ?몄옄瑜?湲곕줉?섍퀬 ?쇰큺 fixture瑜?諛섑솚?쒕떎."""
            yfinance_calls.append({"symbol": symbol, "period": period, "interval": interval})
            return daily_df

        fetcher = MultiTimeframeFetcher(
            api_client_factory=lambda market: client,
            yfinance_history_fetcher=fetch_history,
            yfinance_daily_period="6mo",
        )

        dataset = fetcher.fetch_symbol("AAPL", market="US", exchange="NASD")

        self.assertTrue(dataset.get(Timeframe.MINUTE_5).is_success)
        self.assertTrue(dataset.get(Timeframe.HOUR_1).is_success)
        self.assertTrue(dataset.get(Timeframe.DAY_1).is_success)
        self.assertEqual([call["interval"] for call in client.minute_calls], [5, 60])
        self.assertEqual(client.minute_calls[0]["exchange"], "NASD")
        self.assertEqual(dataset.get(Timeframe.DAY_1).source, "yfinance:history:1d")
        self.assertEqual(yfinance_calls, [{"symbol": "AAPL", "period": "6mo", "interval": "1d"}])

    def test_us_hourly_falls_back_to_resampled_five_minute_data(self) -> None:
        """US 60분 API 실패 시 성공한 5분봉을 60분으로 resample한다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="US")
        client.minute_results[5] = _make_prices("AAPL", n=24, freq="5min")
        client.minute_results[60] = RuntimeError("60분 실패")
        fetcher = MultiTimeframeFetcher(
            api_client_factory=lambda market: client,
            yfinance_history_fetcher=lambda symbol, period, interval: _make_yfinance_daily(),
        )

        dataset = fetcher.fetch_symbol("AAPL", market="US")

        self.assertTrue(dataset.get(Timeframe.HOUR_1).is_success)
        self.assertEqual(dataset.get(Timeframe.HOUR_1).source, "kis:us:5m:resample:60min")
        self.assertEqual(len(dataset.get(Timeframe.HOUR_1).data), 2)

    def test_one_timeframe_failure_does_not_fail_entire_dataset(self) -> None:
        """일부 timeframe 실패는 해당 error에만 남고 나머지 데이터는 유지된다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="US")
        client.minute_results[5] = _make_prices("AAPL", n=12, freq="5min")
        client.minute_results[60] = _make_prices("AAPL", n=2, freq="60min")
        fetcher = MultiTimeframeFetcher(
            api_client_factory=lambda market: client,
            yfinance_history_fetcher=lambda symbol, period, interval: pd.DataFrame(),
        )

        dataset = fetcher.fetch_symbol("AAPL", market="US")

        self.assertTrue(dataset.get(Timeframe.MINUTE_5).is_success)
        self.assertTrue(dataset.get(Timeframe.HOUR_1).is_success)
        self.assertFalse(dataset.get(Timeframe.DAY_1).is_success)
        self.assertIn("insufficient_data", dataset.get(Timeframe.DAY_1).error)
        self.assertEqual(set(dataset.successful_ohlcv().keys()), {"5m", "1h"})

    def test_yfinance_extra_columns_are_removed_from_daily_ohlcv(self) -> None:
        """yfinance가 제공하는 추가 컬럼은 표준 OHLCV 계약에서 제거한다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="US")
        client.minute_results[5] = _make_prices("AAPL", n=12, freq="5min")
        client.minute_results[60] = _make_prices("AAPL", n=2, freq="60min")
        daily_df = _make_yfinance_daily()
        daily_df["Dividends"] = [0.0, 0.0]
        daily_df["Stock Splits"] = [0.0, 0.0]
        fetcher = MultiTimeframeFetcher(
            api_client_factory=lambda market: client,
            yfinance_history_fetcher=lambda symbol, period, interval: daily_df,
        )

        dataset = fetcher.fetch_symbol("AAPL", market="US")

        self.assertEqual(
            list(dataset.get(Timeframe.DAY_1).data.columns),
            ["open", "high", "low", "close", "volume"],
        )

    def test_successful_ohlcv_returns_copies(self) -> None:
        """성공 DataFrame dict를 수정해도 dataset 내부 데이터는 변경되지 않는다."""
        from src.analysis.timeframes import MultiTimeframeFetcher, Timeframe

        client = FakeKisClient(market="US")
        client.minute_results[5] = _make_prices("AAPL", n=12, freq="5min")
        client.minute_results[60] = _make_prices("AAPL", n=2, freq="60min")
        fetcher = MultiTimeframeFetcher(
            api_client_factory=lambda market: client,
            yfinance_history_fetcher=lambda symbol, period, interval: _make_yfinance_daily(),
        )
        dataset = fetcher.fetch_symbol("AAPL", market="US")

        frames = dataset.successful_ohlcv()
        frames["5m"].iloc[0, frames["5m"].columns.get_loc("close")] = -1.0

        self.assertNotEqual(dataset.get(Timeframe.MINUTE_5).data.iloc[0]["close"], -1.0)


class TestTimeframePublicApi(unittest.TestCase):
    """timeframes 모듈 공개 API를 검증한다."""

    def test_module_level_fetch_symbol_uses_fetcher_contract(self) -> None:
        """fetch_symbol 공개 함수가 MultiTimeframeDataset을 반환한다."""
        from src.analysis.timeframes import MultiTimeframeDataset, fetch_symbol

        with patch("src.analysis.timeframes.MultiTimeframeFetcher") as mock_cls:
            expected = MultiTimeframeDataset(symbol="AAPL", market="US", exchange="NASD")
            mock_cls.return_value.fetch_symbol.return_value = expected

            result = fetch_symbol("AAPL", market="US", exchange="NASD")

        self.assertIs(result, expected)
        mock_cls.return_value.fetch_symbol.assert_called_once_with(
            "AAPL", market="US", exchange="NASD"
        )

    def test_fetch_symbol_rejects_non_string_public_inputs_with_value_error(self) -> None:
        """public 입력 타입 오류는 AttributeError가 아니라 ValueError로 반환한다."""
        from src.analysis.timeframes import MultiTimeframeFetcher

        fetcher = MultiTimeframeFetcher(api_client_factory=lambda market: FakeKisClient())

        with self.assertRaisesRegex(ValueError, "symbol"):
            fetcher.fetch_symbol(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "market"):
            fetcher.fetch_symbol("005930", market=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "exchange"):
            fetcher.fetch_symbol("AAPL", market="US", exchange=123)  # type: ignore[arg-type]

    def test_fetcher_constructor_rejects_invalid_boundaries(self) -> None:
        """수집 개수와 일봉 lookback 경계값은 1 이상이어야 한다."""
        from src.analysis.timeframes import MultiTimeframeFetcher

        with self.assertRaisesRegex(ValueError, "minute_count"):
            MultiTimeframeFetcher(minute_count=0)
        with self.assertRaisesRegex(ValueError, "daily_lookback_days"):
            MultiTimeframeFetcher(daily_lookback_days=0)
        with self.assertRaisesRegex(ValueError, "yfinance_daily_period"):
            MultiTimeframeFetcher(yfinance_daily_period="")


def _make_yfinance_daily() -> pd.DataFrame:
    """테스트용 yfinance 일봉 DataFrame을 생성한다."""
    return pd.DataFrame(
        {
            "Open": [180.0, 181.0],
            "High": [182.0, 183.0],
            "Low": [179.0, 180.0],
            "Close": [181.5, 182.5],
            "Volume": [1000, 1100],
        },
        index=pd.date_range("2024-01-02", periods=2, freq="1D"),
    )


if __name__ == "__main__":
    unittest.main()
