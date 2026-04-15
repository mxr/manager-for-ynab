import argparse
from typing import TYPE_CHECKING

from manager_for_ynab import pending_income
from reconciler_for_ynab import _main as reconciler_main

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manager-for-ynab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reconciler_parser = subparsers.add_parser(
        "reconciler",
        help="Find transactions that reconcile an account to a target balance.",
    )
    reconciler_parser.set_defaults(func=_run_reconciler)

    pending_income_parser = subparsers.add_parser(
        "pending-income", help="Move pending income transactions to today."
    )
    pending_income_parser.set_defaults(func=_run_pending_income)

    return parser


def _run_reconciler(argv: Sequence[str]) -> int:
    return reconciler_main.main(argv, prog="manager-for-ynab reconciler")


def _run_pending_income(argv: Sequence[str]) -> int:
    return pending_income.main(argv, prog="manager-for-ynab pending-income")


def main(argv: Sequence[str] = ()) -> int:
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    return args.func(remaining)
