import argparse
import asyncio
import itertools
import os
import re
import shlex
import sqlite3
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from pathlib import Path
from typing import Never
from typing import TYPE_CHECKING

import aiohttp
from babel.numbers import format_currency
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync
from tldm import tldm

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterable
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab reconciler"

_NEG_BAL_ACCT_TYPES = frozenset(("checking", "savings", "cash"))

_LOCALE_EN_US = "en_US"
_DESCRIPTION = "Find and automatically reconciles unreconciled transactions."


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
    raw_targets: list[Decimal]


@dataclass(frozen=True)
class ReconcileCliRequest:
    mode: str
    account_like: str | None
    account_likes: list[str] | None
    raw_target: Decimal | None
    account_target_pairs: list[str] | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=_PACKAGE, description=_DESCRIPTION)
    parser.add_argument(
        "--mode",
        choices=("single", "batch", "interactive-batch"),
        default="single",
        help="Reconciliation mode. `single` uses --account-like/--target. `batch` uses --account-target-pairs. `interactive-batch` prompts for account patterns and targets.",
    )
    parser.add_argument(
        "--account-like",
        help="SQL LIKE pattern to match account name (must match exactly one account)",
    )
    parser.add_argument(
        "--account-likes",
        nargs="+",
        help="Interactive batch mode only. Space-separated SQL LIKE patterns to match account names before prompting for target balances.",
    )
    parser.add_argument(
        "--target",
        type=_parse_target,
        help="Target balance to match towards for reconciliation",
    )
    parser.add_argument(
        "--account-target-pairs",
        nargs="+",
        help="Batch mode only. Account pattern/target pairs in `ACCOUNT_LIKE=TARGET` format (example: `Checking%%=500.30`).",
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
    return parser


async def async_run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    args = build_parser().parse_args(argv)
    for_real: bool = args.for_real
    db: Path = args.sqlite_export_for_ynab_db
    full_refresh: bool = args.sqlite_export_for_ynab_full_refresh
    target_set = _resolve_target_set(
        ReconcileCliRequest(
            mode=args.mode,
            account_like=args.account_like,
            account_likes=args.account_likes,
            raw_target=args.target,
            account_target_pairs=args.account_target_pairs,
        )
    )
    account_likes = target_set.account_likes
    raw_targets = target_set.raw_targets

    token = resolve_token(token_override)

    print("** Refreshing SQLite DB **")
    await sync(token, db, full_refresh)
    print("** Done **")

    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row

        cur = con.cursor()

        plan_accts = fetch_plan_accts(cur, account_likes)
        transactions = fetch_transactions(cur, plan_accts)

    rets = list(
        await asyncio.gather(
            *(
                asyncio.create_task(
                    _reconcile_account(
                        token,
                        acct,
                        txns,
                        rt * (-1 if acct.account_type in _NEG_BAL_ACCT_TYPES else 1),
                        for_real,
                    )
                )
                for rt, acct, txns in zip(
                    raw_targets, plan_accts, transactions, strict=True
                )
            )
        )
    )

    print("Done.")

    return max(rets)


def _parse_account_targets(
    account_target_pairs: list[str],
) -> ReconcileTargetSet:
    account_likes: list[str] = []
    raw_targets: list[Decimal] = []
    for pair in account_target_pairs:
        account_like, _, target = pair.partition("=")
        account_likes.append(_normalize_account_like(account_like))
        raw_targets.append(_parse_target(target))
    return ReconcileTargetSet(account_likes=account_likes, raw_targets=raw_targets)


def _parse_target(target: str) -> Decimal:
    return Decimal(re.sub("[,$]", "", target))


def _resolve_target_set(request: ReconcileCliRequest) -> ReconcileTargetSet:
    mode = request.mode
    if mode == "single":
        _assert_mode_only(
            mode,
            account_likes=request.account_likes,
            account_target_pairs=request.account_target_pairs,
        )
        if request.account_like is None or request.raw_target is None:
            raise ValueError(
                "`--mode single` requires both `--account-like` and `--target`."
            )
        return ReconcileTargetSet(
            account_likes=[_normalize_account_like(request.account_like)],
            raw_targets=[request.raw_target],
        )

    if mode == "batch":
        _assert_mode_only(
            mode,
            account_like=request.account_like,
            account_likes=request.account_likes,
            raw_target=request.raw_target,
        )
        if not request.account_target_pairs:
            raise ValueError("`--mode batch` requires `--account-target-pairs`.")
        return _parse_account_targets(request.account_target_pairs)

    assert mode == "interactive-batch"
    _assert_mode_only(
        mode,
        account_like=request.account_like,
        raw_target=request.raw_target,
        account_target_pairs=request.account_target_pairs,
    )
    return _resolve_interactive_batch_target_set(request.account_likes)


def _assert_mode_only(mode: str, **kwargs: object) -> None:
    present_args = sorted(
        f"`--{name.replace('_', '-')}`"
        for name, value in kwargs.items()
        if value is not None and value != []
    )
    if present_args:
        raise ValueError(
            f"`--mode {mode}` cannot be used with {', '.join(present_args)}."
        )


def _resolve_interactive_batch_target_set(
    account_likes: list[str] | None,
) -> ReconcileTargetSet:
    raw_account_likes = account_likes or _prompt_account_likes()
    raw_targets = _prompt_targets(len(raw_account_likes))
    return ReconcileTargetSet(
        account_likes=[
            _normalize_account_like(account_like) for account_like in raw_account_likes
        ],
        raw_targets=[_parse_target(target) for target in raw_targets],
    )


def _prompt_interactive_batch_inputs() -> ReconcileTargetSet:
    return _resolve_interactive_batch_target_set(None)


def _prompt_account_likes() -> list[str]:
    raw_account_likes = shlex.split(
        input("Account LIKE patterns separated by spaces: ").strip()
    )
    if not raw_account_likes:
        raise ValueError(
            "`--mode interactive-batch` requires at least one account LIKE pattern."
        )
    return raw_account_likes


def _prompt_targets(target_count: int) -> list[str]:
    raw_targets = shlex.split(
        input("Target balances in matching order, separated by spaces: ").strip()
    )
    if len(raw_targets) != target_count:
        raise ValueError(
            f"`--mode interactive-batch` requires {target_count} target balances, but got {len(raw_targets)}."
        )
    return raw_targets


def _normalize_account_like(account_like: str) -> str:
    if "%" in account_like or "_" in account_like:
        return account_like

    return f"%{account_like}%"


async def _reconcile_account(
    token: str,
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
            target, currency=plan_acct.currency, locale=_LOCALE_EN_US
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
            token,
            plan_acct.plan_id,
            to_reconcile,
            progress_desc=f"{prefix} Reconciling",
        )

    return 0


def fetch_plan_accts(
    cur: sqlite3.Cursor, account_likes: list[str]
) -> list[PlanAccount]:
    plan_accts = cur.execute(
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
    ).fetchall()

    if len(plan_accts) != len(account_likes):
        raise ValueError(
            f"\n❌ Must have {len(account_likes)} total account matches for the supplied pairs, but instead found: {_pretty(plan_accts)}\nChange account LIKE patterns to be more precise and try again."
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


def _pretty(plan_accts: list[sqlite3.Row]) -> str:
    if not plan_accts:
        return "nothing!"

    return "\n" + "\n".join(
        sorted(f" * {pl['plan_name']} - {pl['account_name']}" for pl in plan_accts)
    )


def fetch_transactions(
    cur: sqlite3.Cursor, plan_accts: list[PlanAccount]
) -> list[list[Transaction]]:
    assert plan_accts

    unreconciled = cur.execute(
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
                AND ({" OR ".join("account_id = ?" for _ in plan_accts)})
            ORDER BY date
            """,
        tuple(pl.account_id for pl in plan_accts),
    ).fetchall()

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

    with tldm[Never](
        total=2 ** len(uncleared), desc=progress_desc, complete_bar_on_early_finish=True
    ) as pbar:
        for n in range(len(uncleared) + 1):
            for combo in itertools.combinations(uncleared, n):
                if (
                    reconciled_balance
                    + sum(t.amount for t in itertools.chain(cleared, combo))
                    == target
                ):
                    return tuple(itertools.chain(cleared, combo)), True
                pbar.update()

    return (), False


async def do_reconcile(
    token: str, plan_id: str, to_reconcile: Sequence[Transaction], progress_desc: str
) -> None:
    yc = YnabClient(token)
    with tldm[Never](total=len(to_reconcile), desc=progress_desc) as pbar:
        async with aiohttp.ClientSession() as session:
            try:
                await yc.reconcile(session, pbar, plan_id, [t.id for t in to_reconcile])
            except Error4034:
                await asyncio.gather(
                    *(
                        yc.reconcile(session, pbar, to_reconcile[0].plan_id, [t.id])
                        for t in to_reconcile
                    )
                )


def partition[T](
    items: Iterable[T], func: Callable[[T], bool]
) -> tuple[list[T], list[T]]:
    trues, falses = [], []
    for i in items:
        if func(i):
            trues.append(i)
        else:
            falses.append(i)
    return trues, falses


class Error4034(Exception):
    """Raised when an internal YNAB rate-limit is reached. A workaround is to reconcile one-at-a-time."""


@dataclass
class YnabClient:
    token: str
    headers: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def reconcile(
        self,
        session: aiohttp.ClientSession,
        pbar: tldm[Never],
        plan_id: str,
        transaction_ids: list[str],
    ) -> None:
        reconciled = [{"id": t, "cleared": "reconciled"} for t in transaction_ids]

        url = f"https://api.ynab.com/v1/plans/{plan_id}/transactions"

        async with session.request(
            "PATCH", url, headers=self.headers, json={"transactions": reconciled}
        ) as resp:
            body = await resp.json()

        if body.get("error", {}).get("id") == "403.4":
            raise Error4034()

        pbar.update(len(transaction_ids))


def run(argv: Sequence[str] | None = None, *, token_override: str | None = None) -> int:
    return asyncio.run(async_run(argv, token_override=token_override))


__all__ = [default_db_path.__name__, run.__name__, sync.__name__]
