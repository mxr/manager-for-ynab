import argparse
from typing import TYPE_CHECKING

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

    return parser


def _run_reconciler(argv: Sequence[str]) -> int:
    return reconciler_main.main(argv, prog="manager-for-ynab reconciler")


def main(argv: Sequence[str] = ()) -> int:
    if argv and argv[0] == "reconciler":
        return _run_reconciler(argv[1:])

    parser = build_parser()
    parser.parse_args(argv)
    raise AssertionError("subcommand parser should have exited")
