"""Execution-mode helpers shared across runtime scripts."""

import argparse
from collections.abc import Callable

LIVE_FLAG_HELP = "legacy alias for --mock-order"
DRY_RUN_FLAG_HELP = "mock broker + dry-run (default)"
MOCK_ORDER_FLAG_HELP = "mock broker + order submission"
REAL_BROKER_FLAG_HELP = "real broker + real order submission"
CONFIRM_ORDER_SUBMISSION_FLAG_HELP = "required with any order-submission mode"
CONFIRM_REAL_BROKER_FLAG_HELP = "required with real broker mode"


def describe_execution_mode(is_mock: bool, dry_run: bool) -> str:
    """Return a concise string describing broker and order execution modes."""
    broker_mode = "mock" if is_mock else "real"
    order_mode = "dry-run" if dry_run else "mock" if is_mock else "real"
    return f"broker={broker_mode}, orders={order_mode}"


def emit_execution_banner(
    *,
    print_fn: Callable[[str], None] | None = None,
    title: str,
    details: list[str],
    is_mock: bool,
    dry_run: bool,
) -> None:
    """Print a consistent execution banner for runtime entrypoints."""
    if print_fn is None:
        print_fn = print

    divider = "=" * 60
    print_fn(divider)
    print_fn(title)
    print_fn(divider)
    for detail in details:
        print_fn(detail)
    print_fn(f"주문 dry-run: {dry_run}")
    print_fn(f"실행 모드: {describe_execution_mode(is_mock, dry_run)}")
    print_fn(divider)


def add_execution_mode_arguments(
    parser: argparse.ArgumentParser,
    *,
    live_flag_help: str = LIVE_FLAG_HELP,
    include_legacy_mode: bool = False,
    legacy_mode_help: str = "legacy alias: mock -> --mock-order, real -> --real-broker",
) -> argparse._MutuallyExclusiveGroup:
    """Attach shared execution-mode CLI arguments to a parser."""
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", default=False, help=DRY_RUN_FLAG_HELP)
    mode_group.add_argument("--mock-order", action="store_true", default=False, help=MOCK_ORDER_FLAG_HELP)
    mode_group.add_argument("--real-broker", action="store_true", default=False, help=REAL_BROKER_FLAG_HELP)
    mode_group.add_argument("--live", action="store_true", default=False, help=live_flag_help)

    if include_legacy_mode:
        parser.add_argument(
            "--mode",
            type=str,
            default=None,
            choices=["mock", "real"],
            help=legacy_mode_help,
        )

    parser.add_argument(
        "--confirm-order-submission",
        action="store_true",
        default=False,
        help=CONFIRM_ORDER_SUBMISSION_FLAG_HELP,
    )
    parser.add_argument(
        "--confirm-real-broker",
        action="store_true",
        default=False,
        help=CONFIRM_REAL_BROKER_FLAG_HELP,
    )

    return mode_group


def resolve_execution_flags(
    args,
    *,
    legacy_mode_attr: str | None = None,
    legacy_mode_map: dict[str, tuple[bool, bool]] | None = None,
) -> tuple[bool, bool]:
    """Resolve CLI flags into (is_mock, dry_run)."""
    if getattr(args, "real_broker", False):
        return False, False
    if getattr(args, "mock_order", False) or getattr(args, "live", False):
        return True, False
    if legacy_mode_attr and legacy_mode_map:
        legacy_mode = getattr(args, legacy_mode_attr, None)
        if legacy_mode in legacy_mode_map:
            return legacy_mode_map[legacy_mode]
    return True, True


def validate_execution_mode_or_exit(
    args,
    *,
    is_mock: bool,
    dry_run: bool,
    print_fn: Callable[[str], None] | None = None,
    real_broker_error: str = "ERROR: --real-broker requires --confirm-real-broker",
) -> None:
    """Validate execution flags and exit for unsafe operator combinations."""
    if print_fn is None:
        print_fn = print

    if not dry_run and not getattr(args, "confirm_order_submission", False):
        print_fn("WARNING: order submission mode selected.")
        print_fn("ERROR: order submission requires --confirm-order-submission")
        raise SystemExit(2)

    if not is_mock:
        print_fn("WARNING: real broker mode selected.")
        print_fn("WARNING: readiness audit does not consider this path fully ready.")
        if not getattr(args, "confirm_real_broker", False):
            print_fn(real_broker_error)
            raise SystemExit(2)


def load_kis_credentials(
    *,
    is_mock: bool,
    getenv: Callable[[str], str | None],
) -> tuple[str | None, str | None, str | None]:
    """Load KIS credentials for the requested broker mode."""
    if is_mock:
        return (
            getenv("KIS_APP_KEY"),
            getenv("KIS_APP_SECRET"),
            getenv("KIS_ACCOUNT_NUMBER"),
        )
    return (
        getenv("KIS_REAL_APP_KEY"),
        getenv("KIS_REAL_APP_SECRET"),
        getenv("KIS_REAL_ACCOUNT_NUMBER"),
    )
