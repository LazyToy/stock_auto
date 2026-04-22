from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from typing import Sequence


BANNER = "[DRY RUN OK] src.crawling.run_daily bootstrap ready"

Step = tuple[str, str]
Caller = Callable[[list[str]], int]

MODE_STEPS: dict[str, tuple[Step, ...]] = {
    "all": (
        ("Daily trend snapshot", "src.crawling.generate_snapshots"),
        ("KR scraper", "src.crawling.stock_scraper"),
        ("US scraper", "src.crawling.us_stock_scraper"),
        ("Backfill 5d return", "src.crawling.backfill_5day_return"),
    ),
    "snapshots": (("Daily trend snapshot", "src.crawling.generate_snapshots"),),
    "kr": (("KR scraper", "src.crawling.stock_scraper"),),
    "us": (("US scraper", "src.crawling.us_stock_scraper"),),
    "backfill": (("Backfill 5d return", "src.crawling.backfill_5day_return"),),
    "backtest": (("Backtest early signal", "src.crawling.backtest_early_signal"),),
}



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawling package daily runner")
    parser.add_argument("--dry-run", action="store_true", help="Validate the package bootstrap only")
    parser.add_argument(
        "--mode",
        choices=tuple(MODE_STEPS),
        default="all",
        help="Select which crawling workflow to run",
    )
    return parser



def main(argv: Sequence[str] | None = None, *, call: Caller = subprocess.call) -> int:
    args = build_parser().parse_args(argv)
    steps = MODE_STEPS[args.mode]

    if args.dry_run:
        print(BANNER)
        print(f"mode={args.mode}")
        for idx, (name, module) in enumerate(steps, start=1):
            print(f"[{idx}/{len(steps)}] {name} - {module}")
        return 0

    for idx, (name, module) in enumerate(steps, start=1):
        print(f"[{idx}/{len(steps)}] {name} - {module}")
        rc = call([sys.executable, "-m", module])
        if rc != 0:
            print(f"[FAIL] {name}: exit code {rc}")
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
