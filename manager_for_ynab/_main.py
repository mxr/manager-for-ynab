import argparse
from typing import TYPE_CHECKING

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

    return parser


def _run_reconciler(argv: Sequence[str]) -> int:
    return reconciler_main.main(argv, prog="manager-for-ynab reconciler")


def main(argv: Sequence[str] = ()) -> int:
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    return args.func(remaining)
