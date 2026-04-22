import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

_HTML_FIXTURE = """
<html><body>
<table class="type2">
<tbody>
<tr><td class="date">2026.04.17</td><td class="num"><span class="tah">+15,234</span></td><td class="num"><span class="tah">-8,450</span></td></tr>
<tr><td class="date">2026.04.16</td><td class="num"><span class="tah">-3,100</span></td><td class="num"><span class="tah">-2,300</span></td></tr>
</tbody>
</table>
</body></html>
"""


def _load_legacy_module():
    module_path = ROOT / "stock_crawling" / "flow_fetcher.py"
    spec = importlib.util.spec_from_file_location("legacy_flow_fetcher", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def test_src_crawling_flow_fetcher_exports_expected_api() -> None:
    module = importlib.import_module("src.crawling.flow_fetcher")

    assert callable(module.parse_foreign_institutional_flow)
    assert callable(module.fetch_flow)
    assert callable(module.fetch_flow_batch)



def test_src_crawling_flow_fetcher_preserves_parse_logic() -> None:
    module = importlib.import_module("src.crawling.flow_fetcher")

    records = module.parse_foreign_institutional_flow(_HTML_FIXTURE)

    assert records[0]["date"] == "2026.04.17"
    assert records[0]["foreign"] == 15234
    assert records[0]["institution"] == -8450



def test_legacy_flow_fetcher_shim_matches_new_module() -> None:
    new_module = importlib.import_module("src.crawling.flow_fetcher")
    legacy_module = _load_legacy_module()

    assert legacy_module.parse_foreign_institutional_flow(_HTML_FIXTURE) == new_module.parse_foreign_institutional_flow(_HTML_FIXTURE)
