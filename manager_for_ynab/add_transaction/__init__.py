import argparse
import asyncio
import datetime
import re
import sys
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import rich
import ynab
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.validation import Validator
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync
from ynab.models.transaction_cleared_status import TransactionClearedStatus

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab add-transaction"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLEARED_CHOICES = {status.name.lower(): status for status in TransactionClearedStatus}


@dataclass(frozen=True)
class ResolvedTransaction:
    plan_id: str
    plan_name: str
    account_id: str
    account_name: str
    account_type: str
    payee_id: str | None
    payee_name: str
    category_id: str | None
    category_name: str | None
    date: datetime.date
    cleared: TransactionClearedStatus
    amount: Decimal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PACKAGE,
        description=(
            "Create a transaction in YNAB and optionally fund a category "
            "from Ready to Assign."
        ),
    )
    parser.add_argument("--plan-name", help="YNAB plan name. If omitted, prompts.")
    parser.add_argument("--account-name", help="Account name. If omitted, prompts.")
    parser.add_argument("--payee-name", help="Payee name. If omitted, prompts.")
    parser.add_argument("--category-name", help="Category name. If omitted, prompts.")
    parser.add_argument(
        "--date",
        type=datetime.date.fromisoformat,
        help="Transaction date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--cleared",
        type=lambda raw: TransactionClearedStatus[raw.upper()],
        choices=_CLEARED_CHOICES,
        help="Cleared status. Defaults to uncleared.",
    )
    parser.add_argument(
        "--amount",
        type=decimal,
        help="Amount in USD. Positive values are expenses.",
    )
    parser.add_argument(
        "--for-real",
        action="store_true",
        help="Create the transaction instead of only previewing it.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages and previews.",
    )
    parser.add_argument(
        "--sqlite-export-for-ynab-db",
        type=Path,
        default=default_db_path(),
        help="Path to sqlite-export-for-ynab SQLite DB file.",
    )
    parser.add_argument(
        "--sqlite-export-for-ynab-full-refresh",
        action="store_true",
        help="Whether to refresh the SQLite DB from scratch.",
    )
    return parser


def decimal(raw_decimal: str) -> Decimal:
    return Decimal(raw_decimal.replace(",", ""))


async def run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    args = build_parser().parse_args(argv)
    return await add_transaction(
        plan_name=args.plan_name,
        account_name=args.account_name,
        payee_name=args.payee_name,
        category_name=args.category_name,
        date=args.date,
        cleared=args.cleared,
        amount=args.amount,
        for_real=args.for_real,
        quiet=args.quiet,
        db=args.sqlite_export_for_ynab_db,
        full_refresh=args.sqlite_export_for_ynab_full_refresh,
        token_override=token_override,
    )


async def add_transaction(
    *,
    plan_name: str | None,
    account_name: str | None,
    payee_name: str | None,
    category_name: str | None,
    date: datetime.date | None,
    cleared: TransactionClearedStatus | None,
    amount: Decimal | None,
    for_real: bool,
    quiet: bool,
    db: Path,
    full_refresh: bool,
    token_override: str | None,
) -> int:
    token = resolve_token(token_override)

    _print("** Refreshing SQLite DB **", quiet=quiet)
    await sync(token, db, full_refresh, quiet=quiet)
    _print("** Done **", quiet=quiet)

    try:
        async with aiosqlite.connect(db) as con:
            con.row_factory = aiosqlite.Row
            await con.create_function("EDITDISTANCE", 2, edit_distance)

            resolved = await _resolve_transaction(
                con,
                plan_name=plan_name,
                account_name=account_name,
                payee_name=payee_name,
                category_name=category_name,
                date=date,
                cleared=cleared,
                amount=amount,
            )

            txn = _build_transaction(resolved)
            if not for_real:
                _print("Dry run, not creating transaction:", quiet=quiet)
                if not quiet:
                    rich.print(txn)
                return 0

            applied_delta = 0
            try:
                with ynab.ApiClient(
                    ynab.Configuration(access_token=token)
                ) as api_client:
                    transactions_api = ynab.TransactionsApi(api_client)
                    await asyncio.to_thread(
                        transactions_api.create_transaction,
                        resolved.plan_id,
                        ynab.PostTransactionsWrapper(transaction=txn),
                    )

                    if (
                        resolved.category_id is not None
                        and resolved.category_name is not None
                        and resolved.category_name == "Inflow: Ready to Assign"
                        and resolved.account_type == "creditCard"
                    ):
                        (
                            payment_category_id,
                            payment_category_name,
                        ) = await _resolve_credit_card_payment_category(
                            con, resolved.plan_id, resolved.account_name
                        )
                        assert txn.amount is not None
                        applied_delta = await _apply_category_budget_delta(
                            api_client,
                            resolved.plan_id,
                            resolved.date,
                            payment_category_id,
                            txn.amount,
                        )
                        _print("Created transaction:", quiet=quiet)
                        if not quiet:
                            rich.print(txn)
                        if applied_delta > 0:
                            print(
                                f"Applied {applied_delta / 1000:.2f} USD to "
                                f"{payment_category_name!r} from Ready to Assign."
                            )
                        if applied_delta < 0:
                            print(
                                f"Returned {abs(applied_delta) / 1000:.2f} USD from "
                                f"{payment_category_name!r} to Ready to Assign."
                            )
                        return 0

                    if (
                        resolved.category_id is not None
                        and resolved.category_name is not None
                        and resolved.category_name != "Inflow: Ready to Assign"
                    ):
                        assert txn.amount is not None
                        applied_delta = await _fund_category(
                            api_client,
                            resolved.plan_id,
                            resolved.date,
                            resolved.category_id,
                            txn.amount,
                        )
            except ynab.ApiException as err:
                print(f"Failed to create transaction: {err}", file=sys.stderr)
                return 1

            _print("Created transaction:", quiet=quiet)
            if not quiet:
                rich.print(txn)

            if (
                resolved.category_id is not None
                and resolved.category_name is not None
                and applied_delta > 0
            ):
                print(
                    f"Funded {resolved.category_name!r} from 'Ready to Assign' "
                    f"by {applied_delta / 1000:.2f} USD"
                )

            return 0
    except RuntimeError as err:
        print(err)
        return 1
    except ValueError as err:
        print(err)
        return 1


async def _resolve_transaction(
    con: aiosqlite.Connection,
    *,
    plan_name: str | None,
    account_name: str | None,
    payee_name: str | None,
    category_name: str | None,
    date: datetime.date | None,
    cleared: TransactionClearedStatus | None,
    amount: Decimal | None,
) -> ResolvedTransaction:
    plans = await _load_name_to_id(con, "plans", deleted=False)
    if not plans:
        raise RuntimeError("No plans found in this YNAB account.")

    if plan_name:
        plan_id = await _matching_entry(con, "plans", plan_name, deleted=False)
        plan_name = next(
            name
            for name, matched_plan_id in plans.items()
            if matched_plan_id == plan_id
        )
    elif len(plans) == 1:
        plan_name, plan_id = next(iter(plans.items()))
    else:
        plan_name = await _choice_prompt("Plan: ", plans)
        plan_id = plans[plan_name]

    current_date = date or await date_prompt()
    account_id = await _resolve_account_id(con, plan_id, account_name)
    resolved_account_name, resolved_account_type = await _load_account_by_id(
        con, account_id
    )
    payee_id, resolved_payee_name, transfer_account_id = await _resolve_payee(
        con, plan_id, payee_name
    )

    resolved_category_id: str | None = None
    resolved_category_name: str | None = None
    if transfer_account_id is not None:
        if category_name:
            raise ValueError("Category not allowed for transfer transactions")
    else:
        resolved_category_id, resolved_category_name = await _resolve_category(
            con, plan_id, category_name
        )

    resolved_amount = amount if amount is not None else await amount_prompt()
    return ResolvedTransaction(
        plan_id=plan_id,
        plan_name=plan_name,
        account_id=account_id,
        account_name=resolved_account_name,
        account_type=resolved_account_type,
        payee_id=payee_id,
        payee_name=resolved_payee_name,
        category_id=resolved_category_id,
        category_name=resolved_category_name,
        date=current_date,
        cleared=cleared or TransactionClearedStatus.UNCLEARED,
        amount=resolved_amount,
    )


def _build_transaction(resolved: ResolvedTransaction) -> ynab.NewTransaction:
    return ynab.NewTransaction(
        account_id=uuid.UUID(resolved.account_id),
        date=resolved.date,
        payee_id=(
            uuid.UUID(resolved.payee_id) if resolved.payee_id is not None else None
        ),
        payee_name=resolved.payee_name,
        amount=int(-1 * 1000 * resolved.amount),
        category_id=(
            uuid.UUID(resolved.category_id)
            if resolved.category_id is not None
            else None
        ),
        cleared=resolved.cleared,
        approved=True,
    )


async def _resolve_account_id(
    con: aiosqlite.Connection, plan_id: str, account_name: str | None
) -> str:
    if account_name:
        return await _matching_entry(con, "accounts", account_name)

    accounts = await _load_name_to_id(con, "accounts", plan_id=plan_id)
    if not accounts:
        raise RuntimeError("No accounts found in this plan.")
    selected_account_name = await _choice_prompt("Account: ", accounts)
    return accounts[selected_account_name]


async def _resolve_category(
    con: aiosqlite.Connection, plan_id: str, category_name: str | None
) -> tuple[str, str]:
    categories = await _load_name_to_id(con, "categories", plan_id=plan_id)
    if not categories:
        raise RuntimeError("No categories found in this plan.")

    if category_name:
        category_id = await _matching_entry(con, "categories", category_name)
        resolved_category_name = next(
            name
            for name, matched_category_id in categories.items()
            if matched_category_id == category_id
        )
        return category_id, resolved_category_name

    selected_category_name = await _choice_prompt("Category: ", categories)
    return categories[selected_category_name], selected_category_name


async def _resolve_payee(
    con: aiosqlite.Connection, plan_id: str, payee_name: str | None
) -> tuple[str | None, str, str | None]:
    payees = await _load_payees(con, plan_id)
    if not payees:
        raise RuntimeError("No payees found in this plan.")

    payee_name_to_entry = {
        name: (payee_id, transfer_account_id)
        for name, payee_id, transfer_account_id in payees
    }

    if payee_name:
        if payee_name in payee_name_to_entry:
            payee_id, transfer_account_id = payee_name_to_entry[payee_name]
            return payee_id, payee_name, transfer_account_id

        try:
            payee_id = await _matching_entry(con, "payees", payee_name)
        except ValueError as err:
            closest_payee = await _closest_match(con, "payees", payee_name)
            prompt = f"Create new payee {payee_name!r}?"
            if closest_payee is not None:
                prompt = f"{prompt} Closest existing payee: {closest_payee[1]!r}."
            if not await confirm(prompt):
                raise ValueError(f"Payee {payee_name!r} was not created") from err
            return None, payee_name, None

        resolved_payee_name, transfer_account_id = next(
            (name, transfer_account_id)
            for name, current_payee_id, transfer_account_id in payees
            if current_payee_id == payee_id
        )
        return payee_id, resolved_payee_name, transfer_account_id

    selected_payee_name = await _choice_prompt("Payee: ", payee_name_to_entry)
    payee_id, transfer_account_id = payee_name_to_entry[selected_payee_name]
    return payee_id, selected_payee_name, transfer_account_id


async def _fund_category(
    api_client: ynab.ApiClient,
    plan_id: str,
    date: datetime.date,
    category_id: str,
    amount: int,
) -> int:
    return await _apply_category_budget_delta(
        api_client, plan_id, date, category_id, max(0, -amount)
    )


async def _apply_category_budget_delta(
    api_client: ynab.ApiClient,
    plan_id: str,
    date: datetime.date,
    category_id: str,
    budget_delta: int,
) -> int:
    if budget_delta == 0:
        return 0

    month = date.replace(day=1)
    categories_api = ynab.CategoriesApi(api_client)
    category = await asyncio.to_thread(
        categories_api.get_month_category_by_id, plan_id, month, category_id
    )
    await asyncio.to_thread(
        categories_api.update_month_category,
        plan_id=plan_id,
        month=month,
        category_id=category_id,
        data=ynab.PatchMonthCategoryWrapper(
            category=ynab.SaveMonthCategory(
                budgeted=category.data.category.budgeted + budget_delta
            )
        ),
    )
    return budget_delta


async def _load_account_by_id(
    con: aiosqlite.Connection, account_id: str
) -> tuple[str, str]:
    async with con.execute(
        """
        SELECT name, type
        FROM accounts
        WHERE id = ? AND NOT deleted
        """,
        (account_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError(f"No account found with id {account_id!r}.")
    return row["name"], row["type"]


async def _resolve_credit_card_payment_category(
    con: aiosqlite.Connection, plan_id: str, account_name: str
) -> tuple[str, str]:
    async with con.execute(
        """
        SELECT name, id
        FROM categories
        WHERE plan_id = ?
          AND NOT deleted
          AND LOWER(category_group_name) LIKE '%credit card%'
          AND name = ?
        """,
        (plan_id, account_name),
    ) as cur:
        rows = list(await cur.fetchall())

    if not rows:
        raise RuntimeError(
            f"No credit card payment category found for account {account_name!r}."
        )
    if len(rows) > 1:
        raise RuntimeError(
            f"Found {len(rows)} credit card payment categories for account "
            f"{account_name!r}."
        )
    row = rows[0]
    return row["id"], row["name"]


async def _load_name_to_id(
    con: aiosqlite.Connection,
    table: str,
    *,
    plan_id: str | None = None,
    deleted: bool = True,
) -> dict[str, str]:
    clauses: list[str] = []
    params: list[str] = []
    if plan_id is not None:
        clauses.append("plan_id = ?")
        params.append(plan_id)
    if deleted:
        clauses.append("NOT deleted")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    async with con.execute(
        f"SELECT name, id FROM {table}{where} ORDER BY LOWER(name)",
        params,
    ) as cur:
        rows = await cur.fetchall()
    return {row["name"]: row["id"] for row in rows}


async def _load_payees(
    con: aiosqlite.Connection, plan_id: str
) -> list[tuple[str, str, str | None]]:
    async with con.execute(
        """
        SELECT name, id, transfer_account_id
        FROM payees
        WHERE plan_id = ? AND NOT deleted
        ORDER BY LOWER(name)
        """,
        (plan_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [(row["name"], row["id"], row["transfer_account_id"]) for row in rows]


async def _matching_entry(
    con: aiosqlite.Connection,
    table: str,
    input_name: str,
    *,
    key_id: str = "id",
    key_name: str = "name",
    deleted: bool = True,
) -> str:
    matched = await _closest_match(
        con,
        table,
        input_name,
        key_id=key_id,
        key_name=key_name,
        deleted=deleted,
    )
    if matched is None:
        raise ValueError(f"No entries found in {table}")

    matched_id, matched_name, is_substring_match, edit_distance = matched
    normalized_edit_pct = edit_distance / max(len(input_name), len(matched_name))
    if not is_substring_match and normalized_edit_pct > 0.2:
        raise ValueError(
            f"No close match for {input_name!r} in {table!r}. "
            f"Closest match was {matched_name!r}, which is too different."
        )
    return matched_id


async def _closest_match(
    con: aiosqlite.Connection,
    table: str,
    input_name: str,
    *,
    key_id: str = "id",
    key_name: str = "name",
    deleted: bool = True,
) -> tuple[str, str, bool, int] | None:
    deleted_clause = " AND NOT deleted" if deleted else ""
    async with con.execute(
        f"""
        SELECT
            {key_id}
            , {key_name}
            , LOWER({key_name}) LIKE '%' || LOWER(?) || '%' AS is_substring_match
            , EDITDISTANCE(LOWER({key_name}), LOWER(?)) AS edit_distance
        FROM {table}
        WHERE 1 = 1{deleted_clause}
        ORDER BY
            CASE
                WHEN is_substring_match THEN 0
                ELSE edit_distance END,
            LENGTH({key_name})
        LIMIT 1
        """,
        (input_name, input_name),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return None
    return (
        row[0],
        row[1],
        bool(row[2]),
        int(row[3]),
    )


async def _choice_prompt(message: str, options: Mapping[str, object]) -> str:
    return await _prompt(
        message,
        lambda text: text in options,
        completer=FuzzyWordCompleter(tuple(options)),
    )


async def date_prompt() -> datetime.date:
    return datetime.date.fromisoformat(
        await _prompt(
            "Date: ",
            lambda text: _DATE_RE.match(text) is not None,
            default=datetime.date.today().isoformat(),
        )
    )


async def amount_prompt() -> Decimal:
    return decimal(
        await _prompt(
            "Amount USD (positive is an expense): ",
            lambda text: bool(text.strip()),
        )
    )


async def confirm(message: str) -> bool:
    return (
        await _prompt(
            f"{message} [y/N]: ",
            lambda text: text.lower() in {"", "y", "yes", "n", "no"},
        )
    ).lower() in {"y", "yes"}


async def _prompt(
    message: str, validator_callable: Callable[[str], bool], **kwargs: object
) -> str:
    session = PromptSession()
    return await session.prompt_async(
        message,
        validator=Validator.from_callable(validator_callable),
        validate_while_typing=False,
        **kwargs,
    )


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


def edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) > len(right):
        left, right = right, left

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[right_index - 1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


__all__ = [add_transaction.__name__, build_parser.__name__, run.__name__]
