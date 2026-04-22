import importlib
from collections.abc import Iterator
import pytest
import sys
from types import ModuleType, SimpleNamespace

import pandas as pd


def _clear_module(module_name: str) -> None:
    sys.modules.pop(module_name, None)


@pytest.fixture(autouse=True)
def _reset_imported_crawling_modules() -> Iterator[None]:
    yield
    _clear_module("src.crawling.stock_scraper")
    _clear_module("src.crawling.us_stock_scraper")
    _clear_module("src.crawling.early_signal")


def _install_stock_scraper_import_stubs(monkeypatch) -> None:
    bs4_module = ModuleType("bs4")
    setattr(bs4_module, "BeautifulSoup", object)

    gspread_module = ModuleType("gspread")
    setattr(gspread_module, "authorize", lambda credentials: SimpleNamespace())
    setattr(
        gspread_module,
        "exceptions",
        SimpleNamespace(WorksheetNotFound=Exception, SpreadsheetNotFound=Exception),
    )

    credentials_cls = type(
        "Credentials",
        (),
        {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())},
    )
    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)

    fdr_module = ModuleType("FinanceDataReader")
    sector_map_module = ModuleType("src.crawling.sector_map_kr")
    setattr(sector_map_module, "SectorMapKR", object)
    streak_module = ModuleType("src.crawling.streak_indicators")
    setattr(streak_module, "compute_indicators", lambda *args, **kwargs: {})

    monkeypatch.setitem(sys.modules, "bs4", bs4_module)
    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)
    monkeypatch.setitem(sys.modules, "src.crawling.sector_map_kr", sector_map_module)
    monkeypatch.setitem(sys.modules, "src.crawling.streak_indicators", streak_module)



def _install_us_scraper_import_stubs(monkeypatch) -> None:
    gspread_module = ModuleType("gspread")
    setattr(gspread_module, "SpreadsheetNotFound", type("SpreadsheetNotFound", (Exception,), {}))
    setattr(gspread_module, "WorksheetNotFound", type("WorksheetNotFound", (Exception,), {}))
    setattr(
        gspread_module,
        "authorize",
        lambda credentials: SimpleNamespace(
            open=lambda name: SimpleNamespace(url=name),
            create=lambda name: SimpleNamespace(url=name),
        ),
    )

    credentials_cls = type(
        "Credentials",
        (),
        {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())},
    )
    service_account_module = ModuleType("google.oauth2.service_account")
    setattr(service_account_module, "Credentials", credentials_cls)
    google_module = ModuleType("google")
    oauth2_module = ModuleType("google.oauth2")
    setattr(oauth2_module, "service_account", service_account_module)
    setattr(google_module, "oauth2", oauth2_module)

    fdr_module = ModuleType("FinanceDataReader")
    streak_module = ModuleType("src.crawling.streak_indicators")
    setattr(streak_module, "compute_indicators", lambda *args, **kwargs: {})

    monkeypatch.setitem(sys.modules, "gspread", gspread_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", service_account_module)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)
    monkeypatch.setitem(sys.modules, "src.crawling.streak_indicators", streak_module)



def _clear_phase3_env(monkeypatch) -> None:
    for name in [
        "CRAWL_KR_SURGE_THRESHOLD",
        "CRAWL_KR_DROP_THRESHOLD",
        "CRAWL_KR_DROP_SECONDARY_THRESHOLD",
        "CRAWL_KR_VOLUME_THRESHOLD",
        "CRAWL_KR_FLUCTUATION_THRESHOLD",
        "CRAWL_US_SURGE_THRESHOLD_LARGE",
        "CRAWL_US_SURGE_THRESHOLD_SMALL",
        "CRAWL_US_DROP_THRESHOLD_LARGE",
        "CRAWL_US_DROP_THRESHOLD_SMALL",
        "CRAWL_US_MARKET_CAP_THRESHOLD",
        "CRAWL_US_VOLUME_THRESHOLD",
        "CRAWL_US_VOLATILITY_THRESHOLD",
        "CRAWL_EARLY_SIGNAL_RVOL_MIN",
        "CRAWL_EARLY_SIGNAL_CHANGE_MIN",
        "CRAWL_EARLY_SIGNAL_CHANGE_MAX",
        "CRAWL_EARLY_SIGNAL_STREAK_MIN",
        "CRAWL_EARLY_SIGNAL_RATIO_52W_MIN",
    ]:
        monkeypatch.delenv(name, raising=False)



def _import_stock_scraper(monkeypatch):
    _clear_phase3_env(monkeypatch)
    _install_stock_scraper_import_stubs(monkeypatch)
    _clear_module("src.crawling.stock_scraper")
    return importlib.import_module("src.crawling.stock_scraper")



def _import_us_stock_scraper(monkeypatch):
    _clear_phase3_env(monkeypatch)
    _install_us_scraper_import_stubs(monkeypatch)
    _clear_module("src.crawling.us_stock_scraper")
    return importlib.import_module("src.crawling.us_stock_scraper")



def _import_early_signal(monkeypatch):
    _clear_phase3_env(monkeypatch)
    _clear_module("src.crawling.early_signal")
    return importlib.import_module("src.crawling.early_signal")



def test_stock_scraper_defaults_are_preserved_without_env(monkeypatch) -> None:
    module = _import_stock_scraper(monkeypatch)

    assert module.CONFIG["SURGE_THRESHOLD"] == 15.0
    assert module.CONFIG["DROP_THRESHOLD"] == -15.0
    assert module.CONFIG["DROP_SECONDARY_THRESHOLD"] == -6.0
    assert module.CONFIG["VOLUME_THRESHOLD"] == 500
    assert module.CONFIG["FLUCTUATION_THRESHOLD"] == 6.0



def test_stock_scraper_reads_env_overrides(monkeypatch) -> None:
    _install_stock_scraper_import_stubs(monkeypatch)
    monkeypatch.setenv("CRAWL_KR_SURGE_THRESHOLD", "21.5")
    monkeypatch.setenv("CRAWL_KR_DROP_THRESHOLD", "-12.5")
    monkeypatch.setenv("CRAWL_KR_DROP_SECONDARY_THRESHOLD", "-4.5")
    monkeypatch.setenv("CRAWL_KR_VOLUME_THRESHOLD", "900")
    monkeypatch.setenv("CRAWL_KR_FLUCTUATION_THRESHOLD", "8.5")
    _clear_module("src.crawling.stock_scraper")

    module = importlib.import_module("src.crawling.stock_scraper")

    assert module.CONFIG["SURGE_THRESHOLD"] == 21.5
    assert module.CONFIG["DROP_THRESHOLD"] == -12.5
    assert module.CONFIG["DROP_SECONDARY_THRESHOLD"] == -4.5
    assert module.CONFIG["VOLUME_THRESHOLD"] == 900
    assert module.CONFIG["FLUCTUATION_THRESHOLD"] == 8.5



def test_stock_scraper_invalid_env_raises_value_error(monkeypatch) -> None:
    _install_stock_scraper_import_stubs(monkeypatch)
    monkeypatch.setenv("CRAWL_KR_VOLUME_THRESHOLD", "bad-int")
    _clear_module("src.crawling.stock_scraper")

    try:
        importlib.import_module("src.crawling.stock_scraper")
    except ValueError as exc:
        assert "CRAWL_KR_VOLUME_THRESHOLD" in str(exc)
        assert "bad-int" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid KR override")



def test_us_stock_scraper_defaults_are_preserved_without_env(monkeypatch) -> None:
    module = _import_us_stock_scraper(monkeypatch)

    assert module.CONFIG["SURGE_THRESHOLD_LARGE"] == 8.0
    assert module.CONFIG["SURGE_THRESHOLD_SMALL"] == 15.0
    assert module.CONFIG["DROP_THRESHOLD_LARGE"] == -8.0
    assert module.CONFIG["DROP_THRESHOLD_SMALL"] == -15.0
    assert module.CONFIG["MARKET_CAP_THRESHOLD"] == 2000000000
    assert module.CONFIG["VOLUME_THRESHOLD"] == 100000000
    assert module.CONFIG["VOLATILITY_THRESHOLD"] == 5.0



def test_us_stock_scraper_reads_env_overrides(monkeypatch) -> None:
    _install_us_scraper_import_stubs(monkeypatch)
    monkeypatch.setenv("CRAWL_US_SURGE_THRESHOLD_LARGE", "10.5")
    monkeypatch.setenv("CRAWL_US_SURGE_THRESHOLD_SMALL", "18.0")
    monkeypatch.setenv("CRAWL_US_DROP_THRESHOLD_LARGE", "-6.5")
    monkeypatch.setenv("CRAWL_US_DROP_THRESHOLD_SMALL", "-11.5")
    monkeypatch.setenv("CRAWL_US_MARKET_CAP_THRESHOLD", "3000000000")
    monkeypatch.setenv("CRAWL_US_VOLUME_THRESHOLD", "250000000")
    monkeypatch.setenv("CRAWL_US_VOLATILITY_THRESHOLD", "7.5")
    _clear_module("src.crawling.us_stock_scraper")

    module = importlib.import_module("src.crawling.us_stock_scraper")

    assert module.CONFIG["SURGE_THRESHOLD_LARGE"] == 10.5
    assert module.CONFIG["SURGE_THRESHOLD_SMALL"] == 18.0
    assert module.CONFIG["DROP_THRESHOLD_LARGE"] == -6.5
    assert module.CONFIG["DROP_THRESHOLD_SMALL"] == -11.5
    assert module.CONFIG["MARKET_CAP_THRESHOLD"] == 3000000000
    assert module.CONFIG["VOLUME_THRESHOLD"] == 250000000
    assert module.CONFIG["VOLATILITY_THRESHOLD"] == 7.5


def test_us_stock_scraper_invalid_env_raises_value_error(monkeypatch) -> None:
    _install_us_scraper_import_stubs(monkeypatch)
    monkeypatch.setenv("CRAWL_US_MARKET_CAP_THRESHOLD", "not-a-number")
    _clear_module("src.crawling.us_stock_scraper")

    try:
        importlib.import_module("src.crawling.us_stock_scraper")
    except ValueError as exc:
        assert "CRAWL_US_MARKET_CAP_THRESHOLD" in str(exc)
        assert "not-a-number" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid US override")


def test_early_signal_defaults_are_preserved_without_env(monkeypatch) -> None:
    module = _import_early_signal(monkeypatch)

    assert module._RVOL_MIN == 3.0
    assert module._CHANGE_MIN == 3.0
    assert module._CHANGE_MAX == 10.0
    assert module._STREAK_MIN == 3
    assert module._RATIO_52W_MIN == 0.95


def test_early_signal_reads_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_RVOL_MIN", "4.5")
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_CHANGE_MIN", "4.0")
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_CHANGE_MAX", "12.5")
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_STREAK_MIN", "5")
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_RATIO_52W_MIN", "0.975")
    _clear_module("src.crawling.early_signal")

    module = importlib.import_module("src.crawling.early_signal")

    assert module._RVOL_MIN == 4.5
    assert module._CHANGE_MIN == 4.0
    assert module._CHANGE_MAX == 12.5
    assert module._STREAK_MIN == 5
    assert module._RATIO_52W_MIN == 0.975


def test_early_signal_invalid_env_raises_value_error(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_STREAK_MIN", "three")
    _clear_module("src.crawling.early_signal")

    try:
        importlib.import_module("src.crawling.early_signal")
    except ValueError as exc:
        assert "CRAWL_EARLY_SIGNAL_STREAK_MIN" in str(exc)
        assert "three" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid early-signal override")


@pytest.mark.parametrize("raw_value", ["nan", "inf", "-inf"])
def test_stock_scraper_non_finite_float_env_raises_value_error(monkeypatch, raw_value: str) -> None:
    _install_stock_scraper_import_stubs(monkeypatch)
    monkeypatch.setenv("CRAWL_KR_SURGE_THRESHOLD", raw_value)
    _clear_module("src.crawling.stock_scraper")

    with pytest.raises(ValueError) as exc_info:
        importlib.import_module("src.crawling.stock_scraper")

    assert "CRAWL_KR_SURGE_THRESHOLD" in str(exc_info.value)
    assert raw_value in str(exc_info.value)


@pytest.mark.parametrize("raw_value", ["nan", "inf", "-inf"])
def test_us_stock_scraper_non_finite_float_env_raises_value_error(monkeypatch, raw_value: str) -> None:
    _install_us_scraper_import_stubs(monkeypatch)
    monkeypatch.setenv("CRAWL_US_VOLATILITY_THRESHOLD", raw_value)
    _clear_module("src.crawling.us_stock_scraper")

    with pytest.raises(ValueError) as exc_info:
        importlib.import_module("src.crawling.us_stock_scraper")

    assert "CRAWL_US_VOLATILITY_THRESHOLD" in str(exc_info.value)
    assert raw_value in str(exc_info.value)


@pytest.mark.parametrize("raw_value", ["nan", "inf", "-inf"])
def test_early_signal_non_finite_float_env_raises_value_error(monkeypatch, raw_value: str) -> None:
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_CHANGE_MAX", raw_value)
    _clear_module("src.crawling.early_signal")

    with pytest.raises(ValueError) as exc_info:
        importlib.import_module("src.crawling.early_signal")

    assert "CRAWL_EARLY_SIGNAL_CHANGE_MAX" in str(exc_info.value)
    assert raw_value in str(exc_info.value)


def test_early_signal_override_changes_signal_logic(monkeypatch) -> None:
    default_module = _import_early_signal(monkeypatch)

    default_result = default_module.is_early_signal(
        change=5.0,
        rvol=4.0,
        streak=3,
        close_ratio_52w=0.80,
    )

    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_RVOL_MIN", "4.5")
    _clear_module("src.crawling.early_signal")
    override_module = importlib.import_module("src.crawling.early_signal")

    override_result = override_module.is_early_signal(
        change=5.0,
        rvol=4.0,
        streak=3,
        close_ratio_52w=0.80,
    )

    assert default_result is True
    assert override_result is False


def test_generate_snapshots_early_signal_source_respects_relaxed_env_overrides(monkeypatch) -> None:
    _clear_phase3_env(monkeypatch)
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_RVOL_MIN", "2.0")
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_CHANGE_MIN", "2.0")
    monkeypatch.setenv("CRAWL_EARLY_SIGNAL_CHANGE_MAX", "15.0")
    _clear_module("src.crawling.early_signal")

    fdr_module = ModuleType("FinanceDataReader")
    listing = pd.DataFrame(
        [
            {
                "Code": "1234",
                "Name": "relaxed-min",
                "Market": "KOSPI",
                "ChagesRatio": 2.5,
                "Amount": 1_000_000_000,
                "Volume": 250,
                "Close": 90,
            },
            {
                "Code": "5678",
                "Name": "relaxed-max",
                "Market": "KOSDAQ",
                "ChagesRatio": 12.5,
                "Amount": 2_000_000_000,
                "Volume": 300,
                "Close": 90,
            },
        ]
    )
    history = pd.DataFrame({"High": [100] * 20})
    setattr(fdr_module, "StockListing", lambda market: listing)
    setattr(fdr_module, "DataReader", lambda ticker, start=None: history)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr_module)

    class FakeOHLCVStore:
        def __init__(self, path: str) -> None:
            self.path = path

        def avg_volume(self, ticker: str, window: int) -> float:
            return 100.0

        def close(self) -> None:
            pass

    ohlcv_module = ModuleType("src.crawling.ohlcv_store")
    setattr(ohlcv_module, "OHLCVStore", FakeOHLCVStore)
    monkeypatch.setitem(sys.modules, "src.crawling.ohlcv_store", ohlcv_module)

    streak_module = ModuleType("src.crawling.streak_indicators")
    setattr(streak_module, "compute_indicators", lambda df: {"streak_days": 3})
    monkeypatch.setitem(sys.modules, "src.crawling.streak_indicators", streak_module)

    module = importlib.import_module("src.crawling.generate_snapshots")

    signals = module._production_early_signal_source({"date": "2026-04-13"}, "2026-04-13")

    assert [signal["ticker"] for signal in signals] == ["001234", "005678"]
    assert [signal["change"] for signal in signals] == [2.5, 12.5]
    assert [signal["rvol"] for signal in signals] == [2.5, 3.0]
