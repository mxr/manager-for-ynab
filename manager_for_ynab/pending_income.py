import argparse
import asyncio
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Never
from typing import TYPE_CHECKING

import rich
import ynab
from rich.table import Table
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync
from tldm import tldm

from manager_for_ynab._version import get_version

if TYPE_CHECKING:
    from collections.abc import Sequence


_ENV_TOKEN = "YNAB_PERSONAL_ACCESS_TOKEN"
_PACKAGE = "manager-for-ynab pending-income"
_PENDING_INCOME_SQL = (
    files("manager_for_ynab").joinpath("pending_income.sql").read_text()
)


@dataclass(frozen=True)
class Transaction:
    id: str
    plan_id: str
    account_name: str
    payee_name: str
    amount_formatted: str
    date: str


def build_parser(*, prog: str = _PACKAGE) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument(
        "--sqlite-export-for-ynab-db", type=Path, default=default_db_path()
    )
    parser.add_argument("--sqlite-export-for-ynab-full-refresh", action="store_true")
    parser.add_argument("--for-real", action="store_true")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {get_version()}"
    )
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = _PACKAGE) -> int:
    args = build_parser(prog=prog).parse_args(argv)
    db: Path = args.sqlite_export_for_ynab_db
    full_refresh: bool = args.sqlite_export_for_ynab_full_refresh
    for_real: bool = args.for_real

    token = os.environ.get(_ENV_TOKEN)
    if not token:
        raise ValueError(
            "Must set YNAB access token as `YNAB_PERSONAL_ACCESS_TOKEN` environment variable. See https://api.ynab.com/#personal-access-tokens"
        )

    print("** Refreshing SQLite DB **")
    asyncio.run(sync(token, db, full_refresh))
    print("** Done **")

    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        txns_by_plan = fetch_pending_income(con.cursor())

    total_txns = sum(len(txns) for txns in txns_by_plan.values())
    print(f"Found {total_txns} income transaction(s) to update.")
    if total_txns == 0:
        return 0

    print_found_txns([txn for txns in txns_by_plan.values() for txn in txns])

    grouped = build_updates(txns_by_plan, date.today())

    if not for_real:
        print("Use --for-real to actually update transactions.")
        return 0

    api_client = ynab.TransactionsApi(
        ynab.ApiClient(ynab.Configuration(access_token=token))
    )

    with tldm[Never](
        total=total_txns, desc=f"Updating {total_txns} transaction(s)"
    ) as progress:
        for plan_id, txns in grouped.items():
            api_client.update_transactions(
                plan_id, ynab.PatchTransactionsWrapper(transactions=txns)
            )
            progress.update(len(txns))

    return 0


def build_updates(
    txns_by_plan: dict[str, list[Transaction]], today: date
) -> dict[str, list[ynab.SaveTransactionWithIdOrImportId]]:
    grouped: dict[str, list[ynab.SaveTransactionWithIdOrImportId]] = defaultdict(list)
    for plan_id, txns in txns_by_plan.items():
        grouped[plan_id].extend(
            ynab.SaveTransactionWithIdOrImportId(id=txn.id, date=today) for txn in txns
        )
    return grouped


def fetch_pending_income(cur: sqlite3.Cursor) -> dict[str, list[Transaction]]:
    txns = cur.execute(_PENDING_INCOME_SQL).fetchall()

    txns_by_plan: dict[str, list[Transaction]] = defaultdict(list)
    for txn in txns:
        txns_by_plan[txn["plan_id"]].append(
            Transaction(
                id=txn["id"],
                plan_id=txn["plan_id"],
                account_name=txn["account_name"],
                payee_name=txn["payee_name"],
                amount_formatted=txn["amount_formatted"],
                date=txn["date"],
            )
        )

    return txns_by_plan


def print_found_txns(found_txns: list[Transaction]) -> None:
    table = Table(title="Pending Income Transactions")
    table.add_column("Date")
    table.add_column("Account")
    table.add_column("Payee")
    table.add_column("Amount", justify="right")

    for txn in found_txns:
        table.add_row(
            txn.date, txn.account_name, txn.payee_name or "", txn.amount_formatted
        )

    rich.print(table)
