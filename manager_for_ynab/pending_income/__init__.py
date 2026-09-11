import argparse
import sys
from collections import defaultdict
from contextlib import AsyncExitStack
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast
from uuid import UUID

import aiosqlite
import rich
from asyncio_for_ynab import ApiClient
from asyncio_for_ynab import Configuration
from asyncio_for_ynab import NewTransaction
from asyncio_for_ynab import PatchTransactionsWrapper
from asyncio_for_ynab import PostTransactionsWrapper
from asyncio_for_ynab import SaveSubTransaction
from asyncio_for_ynab import SaveTransactionWithIdOrImportId
from asyncio_for_ynab import TransactionClearedStatus
from asyncio_for_ynab import TransactionFlagColor
from asyncio_for_ynab import TransactionsApi
from rich.progress import Progress
from rich.table import Table
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab pending-income"
_PENDING_INCOME_SQL = (
    files("manager_for_ynab.pending_income").joinpath("pending_income.sql").read_text()
)


@dataclass(frozen=True)
class SubTransaction:
    amount: int
    payee_id: str | None
    payee_name: str | None
    category_id: str | None
    memo: str | None


@dataclass(frozen=True)
class Transaction:
    id: str
    plan_id: str
    account_id: str | None
    account_name: str
    payee_id: str | None
    payee_name: str | None
    amount: int
    amount_formatted: str
    category_id: str | None
    memo: str | None
    cleared: str
    approved: bool
    flag_color: str | None
    date: str
    subtransactions: tuple[SubTransaction, ...] = ()

    @property
    def is_split(self) -> bool:
        return bool(self.subtransactions)


@dataclass(frozen=True)
class PendingIncomeResult:
    transactions: list[Transaction]
    updated_count: int


async def run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    parser = argparse.ArgumentParser(prog=_PACKAGE)
    parser.add_argument(
        "--sqlite-export-for-ynab-db", type=Path, default=default_db_path()
    )
    parser.add_argument("--sqlite-export-for-ynab-full-refresh", action="store_true")
    parser.add_argument("--sync", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--for-real", action="store_true")
    parser.add_argument("--skip-matched", action="store_true")
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args(argv)
    db = cast("Path", args.sqlite_export_for_ynab_db)
    full_refresh = cast("bool", args.sqlite_export_for_ynab_full_refresh)
    should_sync = cast("bool", args.sync)
    for_real = cast("bool", args.for_real)
    skip_matched = cast("bool", args.skip_matched)
    quiet = cast("bool", args.quiet)

    result = await pending_income(
        db=db,
        full_refresh=full_refresh,
        should_sync=should_sync,
        for_real=for_real,
        skip_matched=skip_matched,
        token_override=token_override,
        quiet=quiet,
    )

    if len(result.transactions) and not for_real:
        _print("Use --for-real to actually update transactions.", quiet=quiet)
        return 0

    return 0


async def pending_income(
    *,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    for_real: bool,
    skip_matched: bool,
    token_override: str | None,
    quiet: bool,
) -> PendingIncomeResult:
    token = resolve_token(token_override)

    if should_sync:
        _print("** Refreshing SQLite DB **", quiet=quiet)
        await sync(token, db, full_refresh, quiet=quiet)
        _print("** Done **", quiet=quiet)

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        txns_by_plan = await fetch_pending_income(con, skip_matched=skip_matched)

    found_txns = [txn for txns in txns_by_plan.values() for txn in txns]
    total_txns = len(found_txns)

    _print(f"Found {total_txns} income transaction(s) to update.", quiet=quiet)
    if found_txns:
        print_found_txns(found_txns, quiet=quiet)

        if for_real:
            today = datetime.now().astimezone().date()
            grouped = build_updates(txns_by_plan, today)
            recreations = build_split_recreations(txns_by_plan, today)
            async with AsyncExitStack() as stack:
                api_client = await stack.enter_async_context(
                    ApiClient(Configuration(access_token=token))
                )
                progress = stack.enter_context(
                    Progress(disable=quiet or not sys.stderr.isatty())
                )

                transactions_api = TransactionsApi(api_client)
                task_id = progress.add_task(
                    f"Updating {total_txns} transaction(s)", total=total_txns
                )
                for plan_id, txns in grouped.items():
                    await transactions_api.update_transactions(
                        plan_id,
                        PatchTransactionsWrapper(transactions=txns),
                    )
                    progress.update(task_id, advance=len(txns))
                for plan_id, recreated_txns in recreations.items():
                    for transaction_id, new_txn in recreated_txns:
                        await transactions_api.delete_transaction(
                            plan_id, transaction_id
                        )
                        await transactions_api.create_transaction(
                            plan_id, PostTransactionsWrapper(transaction=new_txn)
                        )
                        progress.update(task_id, advance=1)
            _print("Done", quiet=quiet)

    return PendingIncomeResult(
        transactions=found_txns,
        updated_count=total_txns if for_real else 0,
    )


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


def build_updates(
    txns_by_plan: dict[str, list[Transaction]], today: date
) -> dict[str, list[SaveTransactionWithIdOrImportId]]:
    grouped: dict[str, list[SaveTransactionWithIdOrImportId]] = defaultdict(list)
    for plan_id, txns in txns_by_plan.items():
        grouped[plan_id].extend(
            SaveTransactionWithIdOrImportId(id=txn.id, date=today)
            for txn in txns
            if not txn.is_split
        )
    return grouped


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value is not None else None


def build_split_recreations(
    txns_by_plan: dict[str, list[Transaction]], today: date
) -> dict[str, list[tuple[str, NewTransaction]]]:
    grouped: dict[str, list[tuple[str, NewTransaction]]] = defaultdict(list)
    for plan_id, txns in txns_by_plan.items():
        for txn in txns:
            if not txn.is_split:
                continue
            grouped[plan_id].append(
                (
                    txn.id,
                    NewTransaction(
                        account_id=_uuid(txn.account_id),
                        date=today,
                        amount=txn.amount,
                        payee_id=_uuid(txn.payee_id),
                        payee_name=txn.payee_name,
                        category_id=_uuid(txn.category_id),
                        memo=txn.memo,
                        cleared=TransactionClearedStatus(txn.cleared),
                        approved=txn.approved,
                        flag_color=(
                            TransactionFlagColor(txn.flag_color)
                            if txn.flag_color is not None
                            else None
                        ),
                        subtransactions=[
                            SaveSubTransaction(
                                amount=sub.amount,
                                payee_id=_uuid(sub.payee_id),
                                payee_name=sub.payee_name,
                                category_id=_uuid(sub.category_id),
                                memo=sub.memo,
                            )
                            for sub in txn.subtransactions
                        ],
                    ),
                )
            )
    return grouped


async def fetch_pending_income(
    con: aiosqlite.Connection, *, skip_matched: bool = False
) -> dict[str, list[Transaction]]:
    async with con.execute(
        _PENDING_INCOME_SQL, {"skip_matched": int(skip_matched)}
    ) as cur:
        rows = await cur.fetchall()

    txns_by_id: dict[str, Transaction] = {}
    order: list[str] = []
    for row in rows:
        txn_id = row["id"]
        if txn_id not in txns_by_id:
            txns_by_id[txn_id] = Transaction(
                id=txn_id,
                plan_id=row["plan_id"],
                account_id=row["account_id"],
                account_name=row["account_name"],
                payee_id=row["payee_id"],
                payee_name=row["payee_name"],
                amount=row["amount"],
                amount_formatted=row["amount_formatted"],
                category_id=row["category_id"],
                memo=row["memo"],
                cleared=row["cleared"],
                approved=bool(row["approved"]),
                flag_color=row["flag_color"],
                date=row["date"],
            )
            order.append(txn_id)

        if row["subtransaction_id"] is not None:
            txns_by_id[txn_id] = replace(
                txns_by_id[txn_id],
                subtransactions=(
                    *txns_by_id[txn_id].subtransactions,
                    SubTransaction(
                        amount=row["subtransaction_amount"],
                        payee_id=row["subtransaction_payee_id"],
                        payee_name=row["subtransaction_payee_name"],
                        category_id=row["subtransaction_category_id"],
                        memo=row["subtransaction_memo"],
                    ),
                ),
            )

    txns_by_plan: dict[str, list[Transaction]] = defaultdict(list)
    for txn_id in order:
        txn = txns_by_id[txn_id]
        txns_by_plan[txn.plan_id].append(txn)

    return txns_by_plan


def print_found_txns(found_txns: list[Transaction], *, quiet: bool) -> None:
    if quiet:
        return

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


__all__ = ["PendingIncomeResult", "pending_income", "run"]
