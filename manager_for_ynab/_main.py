import argparse
import asyncio
import sys
from typing import TYPE_CHECKING

from manager_for_ynab._version import get_version
from manager_for_ynab.auto_approve import run as run_auto_approve
from manager_for_ynab.pending_income import run as run_pending_income
from manager_for_ynab.reconciler import run as run_reconciler
from manager_for_ynab.zero_out import run as run_zero_out

if TYPE_CHECKING:
    from collections.abc import Sequence


_RECONCILER_HELP = "Find and automatically reconciles unreconciled transactions."
_AUTO_APPROVE_HELP = "Approve matched transactions automatically."


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
    reconciler_parser.set_defaults(func=run_reconciler)

    pending_income_parser = subparsers.add_parser(
        "pending-income", help="Move pending income transactions to today."
    )
    pending_income_parser.set_defaults(func=run_pending_income)

    auto_approve_parser = subparsers.add_parser(
        "auto-approve",
        help=_AUTO_APPROVE_HELP,
        description=_AUTO_APPROVE_HELP,
    )
    auto_approve_parser.set_defaults(func=run_auto_approve)

    zero_out_parser = subparsers.add_parser(
        "zero-out",
        help="Set a category's budgeted amount to zero across a month range.",
    )
    zero_out_parser.set_defaults(func=run_zero_out)
    return parser


def main(argv: Sequence[str] = ()) -> int:
    return asyncio.run(async_main(argv))


async def async_main(argv: Sequence[str] = ()) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        build_parser().print_help()
        return 0
    match argv[0]:
        case "reconciler":
            return await run_reconciler(argv[1:])
        case "pending-income":
            return await run_pending_income(argv[1:])
        case "auto-approve":
            return await run_auto_approve(argv[1:])
        case "zero-out":
            return await run_zero_out(argv[1:])

    parser = build_parser()
    parser.parse_args(argv)
    raise AssertionError("subcommand parser should have exited")
