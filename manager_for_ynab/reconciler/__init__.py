from __future__ import annotations

import argparse
import asyncio
import itertools
import os
import re
import shlex
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from typing import override

import aiosqlite
from asyncio_for_ynab import ApiClient
from asyncio_for_ynab import Configuration
from asyncio_for_ynab import PatchTransactionsWrapper
from asyncio_for_ynab import SaveTransactionWithIdOrImportId
from asyncio_for_ynab import TransactionClearedStatus
from asyncio_for_ynab import TransactionsApi
from babel.numbers import format_currency
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.progress import BarColumn
from rich.progress import Progress
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterable
    from collections.abc import Sequence

try:
    from rich.progress import MofNCompleteColumn
# https://github.com/benleb/surepy/issues/240
except ImportError:  # pragma: no cover
    from rich.progress import ProgressColumn
    from rich.progress import Task
    from rich.text import Text

    if TYPE_CHECKING:
        from rich.table import Column

    class MofNCompleteColumn(ProgressColumn):  # type:ignore[no-redef]
        def __init__(self, separator: str = "/", table_column: Column | None = None):
            self.separator = separator
            super().__init__(table_column=table_column)

        @override
        def render(self, task: Task) -> Text:
            """Show completed/total."""
            completed = int(task.completed)
            total = int(task.total) if task.total is not None else "?"
            total_width = len(str(total))
            return Text(
                f"{completed:{total_width}d}{self.separator}{total}",
                style="progress.download",
            )


_PACKAGE = "manager-for-ynab reconciler"

_NEG_BAL_ACCT_TYPES = frozenset(("checking", "savings", "cash"))

_DESCRIPTION = "Find and automatically reconciles unreconciled transactions."

_PROGRESS_COLUMNS = (
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
)


@dataclass(frozen=True)
class Transaction:
    plan_id: str
    id: str
    amount: Decimal
    amount_formatted: str
    payee: str
    cleared: str

    def pretty(self) -> str:
        return f"{self.amount_formatted:>10} - {self.payee}"


@dataclass(frozen=True)
class PlanAccount:
    plan_id: str
    account_name: str
    account_id: str
    account_type: str
    cleared_balance: Decimal
    currency: str


@dataclass(frozen=True)
class ReconcileTargetSet:
    account_likes: list[str]
    targets: list[Decimal]


@dataclass(frozen=True)
class ReconcileCliRequest:
    mode: str
    account_like: str | None
    target: Decimal | None
    account_target_pairs: list[str] | None
    account_likes: list[str] | None

    def validate(
        self, *, should_be_empty: list[str], should_not_be_empty: list[str]
    ) -> None:
        present_args = sorted(
            self._format_arg_name(arg_name)
            for arg_name in should_be_empty
            if getattr(self, arg_name)
        )
        if present_args:
            raise ValueError(
                f"`--mode {self.mode}` cannot be used with {', '.join(present_args)}."
            )

        missing_args = [
            self._format_arg_name(arg_name)
            for arg_name in should_not_be_empty
            if not getattr(self, arg_name)
        ]
        if missing_args:
            raise ValueError(
                f"`--mode {self.mode}` requires {' and '.join(missing_args)}."
            )

    @staticmethod
    def _format_arg_name(arg_name: str) -> str:
        return f"`--{arg_name.replace('_', '-')}`"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=_PACKAGE, description=_DESCRIPTION)
    parser.add_argument(
        "--mode",
        choices=("single", "batch", "interactive-batch"),
        default="single",
        help="Reconciliation mode. `single` uses --account-like/--target. `batch` uses --account-target-pairs. `interactive-batch` uses --account-likes and prompts for targets.",
    )
    parser.add_argument(
        "--account-like",
        help="SQL LIKE pattern to match account name (must match exactly one account)",
    )
    parser.add_argument(
        "--target",
        type=_parse_target,
        help="Target balance to match towards for reconciliation",
    )
    parser.add_argument(
        "--account-target-pairs",
        nargs="+",
        help="Batch mode only. Account pattern/target pairs in `ACCOUNT_LIKE=TARGET` format (example: `Checking=500.30`).",
    )
    parser.add_argument(
        "--account-likes",
        nargs="+",
        help="Interactive batch mode only. Space-separated SQL LIKE patterns to match account names before prompting for target balances.",
    )
    parser.add_argument(
        "--for-real",
        action="store_true",
        help="Whether to actually perform the reconciliation. If unset, this tool only prints the transactions that would be reconciled.",
    )
    parser.add_argument(
        "--sqlite-export-for-ynab-db",
        type=Path,
        default=default_db_path(),
        help="Path to sqlite-export-for-ynab SQLite DB file (respects sqlite-export-for-ynab configuration; if unset, will be %(default)s)",
    )
    parser.add_argument(
        "--sqlite-export-for-ynab-full-refresh",
        action="store_true",
        help="Whether to **DROP ALL TABLES** and fetch all plan data again. If unset, this tool only does an incremental refresh",
    )
    parser.add_argument(
        "--sync",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh the SQLite DB before using it.",
    )
    return parser


async def run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    args = build_parser().parse_args(argv)
    return await reconciler(
        mode=args.mode,
        account_like=args.account_like,
        target=args.target,
        account_target_pairs=args.account_target_pairs,
        account_likes=args.account_likes,
        for_real=args.for_real,
        db=args.sqlite_export_for_ynab_db,
        full_refresh=args.sqlite_export_for_ynab_full_refresh,
        should_sync=args.sync,
        token_override=token_override,
    )


async def reconciler(
    *,
    mode: str,
    account_like: str | None,
    target: Decimal | None,
    account_target_pairs: list[str] | None,
    account_likes: list[str] | None,
    for_real: bool,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    token_override: str | None,
) -> int:
    target_set = await _resolve_target_set(
        ReconcileCliRequest(
            mode=mode,
            account_like=account_like,
            target=target,
            account_target_pairs=account_target_pairs,
            account_likes=account_likes,
        )
    )
    account_likes = target_set.account_likes
    targets = target_set.targets

    token = resolve_token(token_override)

    if should_sync:
        print("** Refreshing SQLite DB **")
        await sync(token, db, full_refresh)
        print("** Done **")

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row

        plan_accts = await fetch_plan_accts(con, account_likes)
        transactions = await fetch_transactions(con, plan_accts)

    async with ApiClient(Configuration(access_token=token)) as api_client:
        transactions_api = TransactionsApi(api_client)
        rets = list(
            await asyncio.gather(
                *(
                    asyncio.create_task(
                        _reconcile_account(
                            transactions_api,
                            acct,
                            txns,
                            t * (-1 if acct.account_type in _NEG_BAL_ACCT_TYPES else 1),
                            for_real,
                        )
                    )
                    for t, acct, txns in zip(
                        targets, plan_accts, transactions, strict=True
                    )
                )
            )
        )

    print("Done.")

    return max(rets)


def _parse_account_targets(account_target_pairs: list[str]) -> ReconcileTargetSet:
    account_likes: list[str] = []
    targets: list[Decimal] = []
    for pair in account_target_pairs:
        account_like, _, raw_target = pair.partition("=")
        account_likes.append(_normalize_account_like(account_like))
        targets.append(_parse_target(raw_target))
    return ReconcileTargetSet(account_likes=account_likes, targets=targets)


def _parse_target(target: str) -> Decimal:
    return Decimal(re.sub("[,$]", "", target))


async def _resolve_target_set(request: ReconcileCliRequest) -> ReconcileTargetSet:
    mode = request.mode
    if mode == "single":
        request.validate(
            should_be_empty=["account_likes", "account_target_pairs"],
            should_not_be_empty=["account_like", "target"],
        )
        assert request.account_like is not None
        assert request.target is not None
        return ReconcileTargetSet(
            account_likes=[_normalize_account_like(request.account_like)],
            targets=[request.target],
        )

    if mode == "batch":
        request.validate(
            should_be_empty=["account_like", "account_likes", "target"],
            should_not_be_empty=["account_target_pairs"],
        )
        assert request.account_target_pairs is not None
        return _parse_account_targets(request.account_target_pairs)

    assert mode == "interactive-batch"
    request.validate(
        should_be_empty=["account_like", "target", "account_target_pairs"],
        should_not_be_empty=["account_likes"],
    )
    assert request.account_likes is not None
    raw_targets = await _prompt_targets(len(request.account_likes))
    return ReconcileTargetSet(
        account_likes=[
            _normalize_account_like(account_like)
            for account_like in request.account_likes
        ],
        targets=[_parse_target(target) for target in raw_targets],
    )


async def _prompt_targets(target_count: int) -> list[str]:
    session: PromptSession[str] = PromptSession()
    with patch_stdout():
        raw_targets = shlex.split(
            await session.prompt_async(
                "Target balances in matching order, separated by spaces: "
            )
        )
    if len(raw_targets) != target_count:
        raise ValueError(
            f"`--mode interactive-batch` requires {target_count} target "
            "balances, but got {len(raw_targets)}."
        )
    return raw_targets


def _normalize_account_like(account_like: str) -> str:
    if "%" in account_like or "_" in account_like:
        return account_like

    return f"%{account_like}%"


async def _reconcile_account(
    transactions_api: TransactionsApi,
    plan_acct: PlanAccount,
    transactions: list[Transaction],
    target: Decimal,
    for_real: bool,
) -> int:
    prefix = f"[{plan_acct.account_name}]"

    to_reconcile, balance_met = find_to_reconcile(
        transactions,
        plan_acct.cleared_balance,
        target,
        progress_desc=f"{prefix} Testing combinations",
    )

    if not to_reconcile:
        if balance_met:
            print(f"{prefix} Balance already reconciled to target")
            return 0
        pretty_target = format_currency(
            target, currency=plan_acct.currency, locale="en_US"
        )
        print(f"{prefix} No match found for target {pretty_target}")
        return 1

    print(
        f"{prefix} Match found:",
        *(
            f"{prefix} * {t.pretty()}"
            for t in sorted(to_reconcile, key=lambda t: t.amount)
        ),
        sep=os.linesep,
    )

    if for_real:
        await do_reconcile(
            transactions_api,
            plan_acct.plan_id,
            to_reconcile,
            progress_desc=f"{prefix} Reconciling",
        )

    return 0


async def fetch_plan_accts(
    con: aiosqlite.Connection, account_likes: list[str]
) -> list[PlanAccount]:
    async with con.execute(
        f"""
            SELECT
                plans.id as plan_id
                , plans.name as plan_name
                , accounts.name as account_name
                , accounts.type as account_type
                , accounts.id as account_id
                , accounts.type as account_type
                , accounts.cleared_balance
                , plans.currency_format_iso_code
            FROM accounts
            JOIN plans
                ON accounts.plan_id = plans.id
            WHERE
                TRUE
                AND NOT deleted
                AND NOT closed
                AND ({" OR ".join("accounts.name LIKE ?" for _ in account_likes)})
            ORDER BY
                CASE
                    {" ".join(f"WHEN accounts.name LIKE ? THEN {i}" for i, _ in enumerate(account_likes))}
                END
            """,
        (*account_likes, *account_likes),
    ) as cur:
        plan_accts = list(await cur.fetchall())

    if len(plan_accts) != len(account_likes):
        raise ValueError(
            f"\n❌ Must have {len(account_likes)} total account matches for the "
            f"supplied pairs, but instead found: {_pretty(plan_accts)}\n"
            "Change account LIKE patterns to be more precise and try again."
        )

    return [
        PlanAccount(
            plan_id=pl["plan_id"],
            account_name=pl["account_name"],
            account_id=pl["account_id"],
            cleared_balance=Decimal(-pl["cleared_balance"]) / 1000,
            account_type=pl["account_type"],
            currency=pl["currency_format_iso_code"],
        )
        for pl in plan_accts
    ]


def _pretty(plan_accts: list[aiosqlite.Row]) -> str:
    if not plan_accts:
        return "nothing!"

    return "\n" + "\n".join(
        sorted(f" * {pl['plan_name']} - {pl['account_name']}" for pl in plan_accts)
    )


async def fetch_transactions(
    con: aiosqlite.Connection, plan_accts: list[PlanAccount]
) -> list[list[Transaction]]:
    assert plan_accts

    async with con.execute(
        f"""
            SELECT
                id
                , plan_id
                , account_id
                , amount
                , amount_formatted
                , payee_name
                , cleared
            FROM transactions
            WHERE
                TRUE
                AND cleared != 'reconciled'
                AND NOT deleted
                AND approved = 1
                AND ({" OR ".join("account_id = ?" for _ in plan_accts)})
            ORDER BY date
            """,
        tuple(pl.account_id for pl in plan_accts),
    ) as cur:
        unreconciled = await cur.fetchall()

    # pre-initalize lists so zip() works later
    grouped: dict[str, list[Transaction]] = {pl.account_id: [] for pl in plan_accts}
    for u in unreconciled:
        grouped[u["account_id"]].append(
            Transaction(
                u["plan_id"],
                u["id"],
                Decimal(-u["amount"]) / 1000,
                u["amount_formatted"],
                u["payee_name"],
                u["cleared"],
            )
        )

    return list(grouped.values())


def find_to_reconcile(
    transactions: list[Transaction],
    account_balance: Decimal,
    target: Decimal,
    progress_desc: str,
) -> tuple[tuple[Transaction, ...], bool]:
    cleared, uncleared = partition(transactions, lambda t: t.cleared == "cleared")

    reconciled_balance = account_balance - sum(t.amount for t in cleared)
    if reconciled_balance == target and not cleared:
        return (), True

    total = 2 ** len(uncleared)
    with Progress(
        *_PROGRESS_COLUMNS,
        disable=not sys.stderr.isatty(),
    ) as progress:
        task_id = progress.add_task(progress_desc, total=total)
        for n in range(len(uncleared) + 1):
            for combo in itertools.combinations(uncleared, n):
                amt = sum(t.amount for t in itertools.chain(cleared, combo))
                if reconciled_balance + amt == target:
                    progress.update(task_id, completed=total)
                    return tuple(itertools.chain(cleared, combo)), True
                progress.update(task_id, advance=1)

    return (), False


async def do_reconcile(
    transactions_api: TransactionsApi,
    plan_id: str,
    to_reconcile: Sequence[Transaction],
    progress_desc: str,
) -> None:
    with Progress(*_PROGRESS_COLUMNS, disable=not sys.stderr.isatty()) as progress:
        task_id = progress.add_task(progress_desc, total=len(to_reconcile))
        await transactions_api.update_transactions(
            plan_id,
            PatchTransactionsWrapper(
                transactions=[
                    SaveTransactionWithIdOrImportId(
                        id=t.id, cleared=TransactionClearedStatus.RECONCILED
                    )
                    for t in to_reconcile
                ]
            ),
        )
        progress.update(task_id, advance=len(to_reconcile))


def partition[T](
    items: Iterable[T], func: Callable[[T], bool]
) -> tuple[list[T], list[T]]:
    parts = defaultdict(list)
    for i in items:
        parts[func(i)].append(i)
    return parts[True], parts[False]


__all__ = [reconciler.__name__, run.__name__, sync.__name__]
