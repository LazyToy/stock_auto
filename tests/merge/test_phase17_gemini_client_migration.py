import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "gemini_client.py"
    spec = importlib.util.spec_from_file_location("legacy_gemini_client", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_gemini_client_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.gemini_client")

    assert callable(module.load_api_key)
    assert callable(module.load_api_keys)
    assert callable(module.call_gemini)
    assert callable(module.call_gemini_with_fallback)
    assert callable(module.make_gemini_fn)



def test_src_crawling_gemini_client_preserves_happy_path_logic() -> None:
    module = importlib.import_module("src.crawling.gemini_client")

    result = module.call_gemini("prompt", api_key="key", http_post=lambda url, body: {"candidates": [{"content": {"parts": [{"text": "요약 텍스트"}]}}]})

    assert result == "요약 텍스트"



def test_legacy_gemini_client_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.gemini_client")
    legacy_module = _load_legacy_module()

    assert legacy_module.call_gemini("prompt", api_key="key", http_post=lambda url, body: {"candidates": [{"content": {"parts": [{"text": "요약 텍스트"}]}}]}) == new_module.call_gemini("prompt", api_key="key", http_post=lambda url, body: {"candidates": [{"content": {"parts": [{"text": "요약 텍스트"}]}}]})
