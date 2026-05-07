import argparse
import asyncio
import json
import sys
from collections import defaultdict
from contextlib import AsyncExitStack
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import cast
from typing import TYPE_CHECKING

import aiosqlite
import rich
from asyncio_for_ynab import ApiClient
from asyncio_for_ynab import Configuration
from asyncio_for_ynab import PatchTransactionsWrapper
from asyncio_for_ynab import SaveTransactionWithIdOrImportId
from asyncio_for_ynab import TransactionsApi
from rich.progress import Progress
from rich.table import Table
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab auto-approve"
_MAX_CONCURRENT_REQUESTS = 5
_AUTO_APPROVE_SQL = (
    files("manager_for_ynab.auto_approve").joinpath("auto_approve.sql").read_text()
)


@dataclass(frozen=True)
class Transaction:
    id: str
    plan_id: str
    account_name: str
    payee_name: str
    amount_formatted: str
    date: str
    should_delete: bool = False


@dataclass(frozen=True)
class AutoApproveResult:
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
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args(argv)
    db: Path = args.sqlite_export_for_ynab_db
    full_refresh: bool = args.sqlite_export_for_ynab_full_refresh
    should_sync: bool = args.sync
    for_real: bool = args.for_real
    quiet: bool = args.quiet

    result = await auto_approve(
        db=db,
        full_refresh=full_refresh,
        should_sync=should_sync,
        for_real=for_real,
        token_override=token_override,
        quiet=quiet,
    )

    if len(result.transactions) and not for_real:
        _print("Use --for-real to actually update transactions.", quiet=quiet)

    return 0


async def auto_approve(
    *,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    for_real: bool,
    token_override: str | None,
    quiet: bool,
) -> AutoApproveResult:
    token = resolve_token(token_override)

    if should_sync:
        _print("** Refreshing SQLite DB **", quiet=quiet)
        await sync(token, db, full_refresh, quiet=quiet)
        _print("** Done **", quiet=quiet)

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found_txns = await fetch_auto_approve_transactions(con)

    total_txns = len(found_txns)

    _print(f"Found {total_txns} transaction(s) to update.", quiet=quiet)
    if found_txns:
        print_found_txns(found_txns, quiet=quiet)

        if for_real:
            txns_by_plan: defaultdict[
                str, tuple[list[str], list[SaveTransactionWithIdOrImportId]]
            ] = defaultdict(lambda: ([], []))
            for txn in found_txns:
                delete_txn_ids, update_txns = txns_by_plan[txn.plan_id]
                if txn.should_delete:
                    delete_txn_ids.append(txn.id)
                else:
                    update_txns.append(
                        SaveTransactionWithIdOrImportId(id=txn.id, approved=True)
                    )

            async with AsyncExitStack() as stack:
                api_client = await stack.enter_async_context(
                    ApiClient(Configuration(access_token=token))
                )
                progress = stack.enter_context(
                    Progress(disable=quiet or not sys.stderr.isatty())
                )

                transactions_api = TransactionsApi(api_client)
                semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
                task_id = progress.add_task(
                    f"Updating {total_txns} transaction(s)",
                    total=total_txns,
                )

                async def delete_transaction(plan_id: str, txn_id: str) -> None:
                    async with semaphore:
                        await transactions_api.delete_transaction(plan_id, txn_id)
                        progress.update(task_id, advance=1)

                async def update_transactions(
                    plan_id: str, update_txns: list[SaveTransactionWithIdOrImportId]
                ) -> None:
                    if not update_txns:
                        return

                    async with semaphore:
                        await transactions_api.update_transactions(
                            plan_id,
                            PatchTransactionsWrapper(transactions=update_txns),
                        )
                        progress.update(task_id, advance=len(update_txns))

                requests: list[asyncio.Task[None]] = []
                for plan_id, (delete_txn_ids, update_txns) in txns_by_plan.items():
                    for txn_id in delete_txn_ids:
                        requests.append(
                            asyncio.create_task(delete_transaction(plan_id, txn_id))
                        )

                    requests.append(
                        asyncio.create_task(update_transactions(plan_id, update_txns))
                    )

                await asyncio.gather(*requests)
            _print("Done", quiet=quiet)

    return AutoApproveResult(
        transactions=found_txns,
        updated_count=total_txns if for_real else 0,
    )


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


async def fetch_auto_approve_transactions(
    con: aiosqlite.Connection,
) -> list[Transaction]:
    async with con.execute(_AUTO_APPROVE_SQL) as cur:
        txns = await cur.fetchall()

    return [_transaction_from_row(dict(txn)) for txn in txns]


def _transaction_from_row(txn: dict[str, object]) -> Transaction:
    return Transaction(
        id=cast("str", txn["id"]),
        plan_id=cast("str", txn["plan_id"]),
        account_name=cast("str", txn["account_name"]),
        payee_name=cast("str", txn["payee_name"]),
        amount_formatted=cast("str", txn["amount_formatted"]),
        date=cast("str", txn["date"]),
        should_delete=_is_json_dict(txn["import_payee_name"]),
    )


def _is_json_dict(value: object) -> bool:
    if not isinstance(value, str):
        return False

    try:
        return isinstance(json.loads(value), dict)
    except json.JSONDecodeError:
        return False


def print_found_txns(found_txns: list[Transaction], *, quiet: bool) -> None:
    if quiet:
        return

    table = Table(title="Transactions To Update")
    table.add_column("Action")
    table.add_column("Date")
    table.add_column("Account")
    table.add_column("Payee")
    table.add_column("Amount", justify="right")

    for txn in found_txns:
        table.add_row(
            "Delete" if txn.should_delete else "Update",
            txn.date,
            txn.account_name,
            txn.payee_name or "",
            txn.amount_formatted,
        )

    rich.print(table)


__all__ = [AutoApproveResult.__name__, auto_approve.__name__, run.__name__]
