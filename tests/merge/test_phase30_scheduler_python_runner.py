from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCHEDULE = ROOT / "stock_crawling" / "scripts" / "install_schedule.ps1"


def _install_schedule_text() -> str:
    return INSTALL_SCHEDULE.read_text(encoding="utf-8")


def test_phase6_scheduler_invokes_python_package_runner_not_node_bridge() -> None:
    text = _install_schedule_text()

    assert "src.crawling.run_daily" in text
    assert "runners/run_daily.ts" not in text
    assert "npx" not in text
    assert "tsx" not in text


def test_phase6_scheduler_registers_market_specific_runner_modes() -> None:
    text = _install_schedule_text()

    assert 'Register-StockTask -TaskName "StockCrawling_KR_Daily" -TriggerTime "15:40" -Mode "kr"' in text
    assert 'Register-StockTask -TaskName "StockCrawling_US_Daily" -TriggerTime "06:10" -Mode "us"' in text
    assert "--mode $Mode" in text


def test_phase6_scheduler_writes_logs_under_root_crawling_log_dir() -> None:
    text = _install_schedule_text()

    assert 'Join-Path $ProjectDir "logs"' in text
    assert 'Join-Path $LogRoot "crawling"' in text


def test_phase6_node_daily_runner_bridge_is_removed() -> None:
    assert not (ROOT / "stock_crawling" / "runners" / "run_daily.ts").exists()


def test_phase6_node_package_manifests_are_removed() -> None:
    assert not (ROOT / "stock_crawling" / "package.json").exists()
    assert not (ROOT / "stock_crawling" / "package-lock.json").exists()


def test_phase6_react_vite_root_files_are_removed() -> None:
    assert not (ROOT / "stock_crawling" / "index.html").exists()
    assert not (ROOT / "stock_crawling" / "vite.config.ts").exists()
    assert not (ROOT / "stock_crawling" / "tsconfig.json").exists()


def test_phase6_react_and_node_server_directories_are_removed() -> None:
    assert not (ROOT / "stock_crawling" / "src").exists()
    assert not (ROOT / "stock_crawling" / "server").exists()


def test_phase6_node_runner_directory_is_removed() -> None:
    assert not (ROOT / "stock_crawling" / "runners").exists()


def test_phase6_no_typescript_or_javascript_runtime_files_remain() -> None:
    remaining = [
        path
        for path in (ROOT / "stock_crawling").rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    ]

    assert remaining == []


def test_phase6_active_docs_point_to_python_runner_not_node_tooling() -> None:
    docs = [
        ROOT / "stock_crawling" / "README.md",
        ROOT / "stock_crawling" / "scripts" / "README_schedule.md",
        ROOT / "stock_crawling" / "CLAUDE.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8").lower()
        assert "src.crawling.run_daily" in text
        assert "npx" not in text
        assert "tsx" not in text
        assert "npm " not in text


def test_phase6_historical_node_react_notes_are_legacy_docs() -> None:
    legacy_dir = ROOT / "docs" / "legacy_stock_crawling"
    for filename in ("harnes.md", "harnes_template.md", "result.md"):
        assert not (ROOT / "stock_crawling" / filename).exists()
        assert (legacy_dir / filename).exists()
