from pathlib import Path

import pandas as pd

from src.optimization.automl_support import (
    configure_yfinance_cache,
    download_automl_price_history,
    extract_fitness_history,
    normalize_automl_symbol,
)


class _FakeTicker:
    def __init__(self, symbol, history_map, errors=None):
        self.symbol = symbol
        self._history_map = history_map
        self._errors = errors or {}

    def history(self, period="1y"):
        error = self._errors.get(self.symbol)
        if error is not None:
            raise error
        return self._history_map.get(self.symbol, pd.DataFrame())


class _FakeYFinance:
    def __init__(self, history_map, errors=None):
        self.history_map = history_map
        self.errors = errors or {}
        self.cache_dir = None

    def Ticker(self, symbol):
        return _FakeTicker(symbol, self.history_map, self.errors)

    def set_tz_cache_location(self, cache_dir):
        self.cache_dir = cache_dir


def test_normalize_automl_symbol_for_korean_ticker():
    cleaned_symbol, candidates = normalize_automl_symbol("005930")

    assert cleaned_symbol == "005930"
    assert candidates == ["005930.KS", "005930.KQ"]


def test_normalize_automl_symbol_strips_and_uppercases_us_ticker():
    cleaned_symbol, candidates = normalize_automl_symbol(" aapl ")

    assert cleaned_symbol == "AAPL"
    assert candidates == ["AAPL"]


def test_configure_yfinance_cache_uses_workspace_directory(tmp_path):
    fake_yf = _FakeYFinance({})

    cache_dir = configure_yfinance_cache(fake_yf, base_dir=str(tmp_path))

    assert fake_yf.cache_dir == cache_dir
    assert Path(cache_dir).exists()
    assert Path(cache_dir).is_dir()


def test_download_automl_price_history_retries_kq_when_ks_is_empty(tmp_path):
    expected_df = pd.DataFrame({"Close": [1, 2, 3]})
    fake_yf = _FakeYFinance(
        {
            "005930.KS": pd.DataFrame(),
            "005930.KQ": expected_df,
        }
    )

    df, resolved_symbol, error_message = download_automl_price_history(
        "005930",
        yf_module=fake_yf,
        base_dir=str(tmp_path),
    )

    assert error_message is None
    assert resolved_symbol == "005930.KQ"
    pd.testing.assert_frame_equal(df, expected_df)


def test_download_automl_price_history_returns_validation_message_for_blank_symbol(tmp_path):
    fake_yf = _FakeYFinance({})

    df, resolved_symbol, error_message = download_automl_price_history(
        "   ",
        yf_module=fake_yf,
        base_dir=str(tmp_path),
    )

    assert df.empty
    assert resolved_symbol is None
    assert error_message == "종목 코드를 입력하세요."


def test_extract_fitness_history_converts_values_to_plain_float():
    class _FakeLogbook:
        def select(self, name):
            assert name == "max"
            return [1, 2.5, 3.75]

    history = extract_fitness_history(_FakeLogbook())

    assert history == [1.0, 2.5, 3.75]


def test_extract_fitness_history_falls_back_to_best_fitness_when_needed():
    history = extract_fitness_history(None, fallback_fitness=1.23)

    assert history == [1.23]
