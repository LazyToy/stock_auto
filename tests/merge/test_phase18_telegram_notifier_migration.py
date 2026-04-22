import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "telegram_notifier.py"
    spec = importlib.util.spec_from_file_location("legacy_telegram_notifier", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_telegram_notifier_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.telegram_notifier")

    assert hasattr(module, "TelegramNotifier")
    assert callable(module.should_notify_kr_surge)
    assert callable(module.should_notify_theme_cluster)
    assert callable(module.format_surge_message)



def test_src_crawling_telegram_notifier_preserves_notify_logic() -> None:
    module = importlib.import_module("src.crawling.telegram_notifier")

    assert module.should_notify_kr_surge(5) is True
    assert module.should_notify_theme_cluster([{"intensity_stars": "★★★★☆"}]) is True



def test_legacy_telegram_notifier_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.telegram_notifier")
    legacy_module = _load_legacy_module()

    assert legacy_module.should_notify_kr_surge(5) == new_module.should_notify_kr_surge(5)
    assert legacy_module.format_surge_message("2026-04-17", 7, ["A", "B"]) == new_module.format_surge_message("2026-04-17", 7, ["A", "B"])
