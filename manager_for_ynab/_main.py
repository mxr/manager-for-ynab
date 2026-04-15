import argparse
from typing import TYPE_CHECKING

from manager_for_ynab import pending_income
from manager_for_ynab import zero_out
from manager_for_ynab._version import get_version
from reconciler_for_ynab import _main as reconciler_main

if TYPE_CHECKING:
    from collections.abc import Sequence


_RECONCILER_HELP = "Find and automatically reconciles unreconciled transactions."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manager-for-ynab")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {get_version()}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reconciler_parser = subparsers.add_parser(
        "reconciler",
        help=_RECONCILER_HELP,
        description=_RECONCILER_HELP,
    )
    reconciler_parser.set_defaults(func=_run_reconciler)

    pending_income_parser = subparsers.add_parser(
        "pending-income", help="Move pending income transactions to today."
    )
    pending_income_parser.set_defaults(func=_run_pending_income)

    zero_out_parser = subparsers.add_parser(
        "zero-out",
        help="Set a category's budgeted amount to zero across a month range.",
    )
    zero_out_parser.set_defaults(func=_run_zero_out)
    return parser


def _run_reconciler(argv: Sequence[str]) -> int:
    return reconciler_main.main(argv, prog="manager-for-ynab reconciler")


def _run_pending_income(argv: Sequence[str]) -> int:
    return pending_income.main(argv, prog="manager-for-ynab pending-income")


def _run_zero_out(argv: Sequence[str]) -> int:
    return zero_out.main(argv, prog="manager-for-ynab zero-out")


def main(argv: Sequence[str] = ()) -> int:
    if not argv:
        build_parser().print_help()
        return 0
<<<<<<< HEAD
    if argv[0] == "reconciler":
        return _run_reconciler(argv[1:])
    if argv[0] == "pending-income":
        return _run_pending_income(argv[1:])
    if argv[0] == "zero-out":
=======
    if argv and argv[0] == "reconciler":
        return _run_reconciler(argv[1:])
    if argv and argv[0] == "pending-income":
        return _run_pending_income(argv[1:])
    if argv and argv[0] == "zero-out":
>>>>>>> e7bb582 (Refine reconciler CLI help and versioning)
        return _run_zero_out(argv[1:])

    parser = build_parser()
    parser.parse_args(argv)
    raise AssertionError("subcommand parser should have exited")
