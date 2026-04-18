import argparse
import asyncio
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

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab pending-income"
_DEFAULT_DB_PATH = default_db_path()
_PENDING_INCOME_SQL = (
    files("manager_for_ynab.pending_income").joinpath("pending_income.sql").read_text()
)


@dataclass(frozen=True)
class Transaction:
    id: str
    plan_id: str
    account_name: str
    payee_name: str
    amount_formatted: str
    date: str


@dataclass(frozen=True)
class PendingIncomeResult:
    transactions: list[Transaction]
    updated_count: int


def run(argv: Sequence[str] | None = None, *, token_override: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=_PACKAGE)
    parser.add_argument(
        "--sqlite-export-for-ynab-db", type=Path, default=_DEFAULT_DB_PATH
    )
    parser.add_argument("--sqlite-export-for-ynab-full-refresh", action="store_true")
    parser.add_argument("--for-real", action="store_true")
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args(argv)
    db: Path = args.sqlite_export_for_ynab_db
    full_refresh: bool = args.sqlite_export_for_ynab_full_refresh
    for_real: bool = args.for_real
    quiet: bool = args.quiet

    result = pending_income(
        db=db,
        full_refresh=full_refresh,
        for_real=for_real,
        token_override=token_override,
        quiet=quiet,
    )

    total_txns = len(result.transactions)
    _print(f"Found {total_txns} income transaction(s) to update.", quiet=quiet)
    if total_txns == 0:
        return 0

    if not quiet:
        print_found_txns(result.transactions)

    if not for_real:
        _print("Use --for-real to actually update transactions.", quiet=quiet)
        return 0

    return 0


def pending_income(
    *,
    db: Path = _DEFAULT_DB_PATH,
    full_refresh: bool = False,
    for_real: bool = False,
    token_override: str | None = None,
    quiet: bool = True,
) -> PendingIncomeResult:
    token = resolve_token(token_override)

    _print("** Refreshing SQLite DB **", quiet=quiet)
    asyncio.run(sync(token, db, full_refresh, quiet=quiet))
    _print("** Done **", quiet=quiet)

    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        txns_by_plan = fetch_pending_income(con.cursor())

    found_txns = [txn for txns in txns_by_plan.values() for txn in txns]
    total_txns = len(found_txns)

    if for_real:
        grouped = build_updates(txns_by_plan, date.today())
        api_client = ynab.TransactionsApi(
            ynab.ApiClient(ynab.Configuration(access_token=token))
        )

        with tldm[Never](
            total=total_txns,
            desc=f"Updating {total_txns} transaction(s)",
            disable=quiet,
        ) as progress:
            for plan_id, txns in grouped.items():
                api_client.update_transactions(
                    plan_id, ynab.PatchTransactionsWrapper(transactions=txns)
                )
                progress.update(len(txns))

    return PendingIncomeResult(
        transactions=found_txns,
        updated_count=total_txns if for_real else 0,
    )


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


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


__all__ = [PendingIncomeResult.__name__, pending_income.__name__, run.__name__]
