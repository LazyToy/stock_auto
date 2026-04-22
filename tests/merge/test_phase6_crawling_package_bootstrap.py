import importlib
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]



def test_run_daily_module_exposes_main() -> None:
    module = importlib.import_module("src.crawling.run_daily")

    assert hasattr(module, "main")



def test_run_daily_dry_run_exits_zero_and_prints_banner(capsys) -> None:
    module = importlib.import_module("src.crawling.run_daily")

    exit_code = module.main(["--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[DRY RUN OK] src.crawling.run_daily bootstrap ready" in captured.out



def test_run_daily_dry_run_accepts_mode_and_prints_plan(capsys) -> None:
    module = importlib.import_module("src.crawling.run_daily")

    exit_code = module.main(["--dry-run", "--mode", "kr"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[DRY RUN OK] src.crawling.run_daily bootstrap ready" in captured.out
    assert "mode=kr" in captured.out
    assert "src.crawling.stock_scraper" in captured.out


def test_run_daily_executes_selected_mode_with_injected_caller(capsys) -> None:
    module = importlib.import_module("src.crawling.run_daily")
    calls = []

    def fake_call(command):
        calls.append(command)
        return 0

    exit_code = module.main(["--mode", "us"], call=fake_call)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [[sys.executable, "-m", "src.crawling.us_stock_scraper"]]
    assert "[1/1] US scraper - src.crawling.us_stock_scraper" in captured.out


def test_run_daily_stops_on_first_failed_step(capsys) -> None:
    module = importlib.import_module("src.crawling.run_daily")

    def fake_call(command):
        return 7

    exit_code = module.main(["--mode", "backfill"], call=fake_call)

    captured = capsys.readouterr()
    assert exit_code == 7
    assert "[FAIL] Backfill 5d return: exit code 7" in captured.out


def test_pyproject_declares_stock_crawling_daily_entrypoint() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["scripts"]["stock-crawling-daily"] == "src.crawling.run_daily:main"



def test_module_invocation_supports_dry_run() -> None:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    result = subprocess.run(
        [str(python), "-m", "src.crawling.run_daily", "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "[DRY RUN OK] src.crawling.run_daily bootstrap ready" in result.stdout
