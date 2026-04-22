import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "flow_signal.py"
    spec = importlib.util.spec_from_file_location("legacy_flow_signal", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_flow_signal_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.flow_signal")

    assert module.FLOW_SIGNAL_HEADERS[0] == "날짜"
    assert callable(module.detect_reversal)
    assert callable(module.build_flow_signal_row)



def test_src_crawling_flow_signal_preserves_reversal_logic() -> None:
    module = importlib.import_module("src.crawling.flow_signal")
    records = [
        {"date": "2026.04.17", "foreign": 15234, "institution": -100},
        {"date": "2026.04.16", "foreign": -3100, "institution": -200},
        {"date": "2026.04.15", "foreign": -5200, "institution": -100},
        {"date": "2026.04.14", "foreign": -2800, "institution": 500},
        {"date": "2026.04.11", "foreign": -1500, "institution": -300},
        {"date": "2026.04.10", "foreign": -900, "institution": -400},
    ]

    signals = module.detect_reversal(records, lookback=5)

    assert any(s["reversal_type"] == "외국인매수전환" for s in signals)



def test_legacy_flow_signal_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.flow_signal")
    legacy_module = _load_legacy_module()
    records = [
        {"date": "2026.04.17", "foreign": 15234, "institution": -100},
        {"date": "2026.04.16", "foreign": -3100, "institution": -200},
        {"date": "2026.04.15", "foreign": -5200, "institution": -100},
        {"date": "2026.04.14", "foreign": -2800, "institution": 500},
        {"date": "2026.04.11", "foreign": -1500, "institution": -300},
        {"date": "2026.04.10", "foreign": -900, "institution": -400},
    ]

    assert legacy_module.FLOW_SIGNAL_HEADERS == new_module.FLOW_SIGNAL_HEADERS
    assert legacy_module.detect_reversal(records, lookback=5) == new_module.detect_reversal(records, lookback=5)
    assert legacy_module.build_flow_signal_row(
        date="2026-04-17",
        ticker="005930",
        name="삼성전자",
        reversal_type="외국인매수전환",
        today_foreign=15234,
        today_institution=-8450,
        prev_days_foreign=[-3100, -5200, -2800, -1500, -900],
        prev_days_institution=[-200, -100, 500, -300, -400],
    ) == new_module.build_flow_signal_row(
        date="2026-04-17",
        ticker="005930",
        name="삼성전자",
        reversal_type="외국인매수전환",
        today_foreign=15234,
        today_institution=-8450,
        prev_days_foreign=[-3100, -5200, -2800, -1500, -900],
        prev_days_institution=[-200, -100, 500, -300, -400],
    )
