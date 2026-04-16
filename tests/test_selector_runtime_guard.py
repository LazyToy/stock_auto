import importlib
import sys

import pytest


def test_selector_download_data_requires_yfinance_when_missing(monkeypatch):
    sys.modules.pop("src.strategies.selector", None)
    module = importlib.import_module("src.strategies.selector")
    monkeypatch.setattr(module, "yf", None, raising=False)

    selector = module.StockSelector(["005930"])

    with pytest.raises(RuntimeError, match="yfinance"):
        selector.download_data()
