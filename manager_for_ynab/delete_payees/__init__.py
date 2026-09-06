import argparse
import sys
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import aiosqlite
import rich
from rich.table import Table
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token
from manager_for_ynab._browser_session import resolve_session_cookie
from manager_for_ynab._browser_session import resolve_session_token
from manager_for_ynab._ynab_sync_api import delete_payee as delete_payee_entity

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab delete-payees"
_UNUSED_PAYEES_QUERY = (
    files("manager_for_ynab.delete_payees").joinpath("unused_payees.sql").read_text()
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PACKAGE,
        description=(
            "Delete one or more payees. YNAB's public API has no payee-delete "
            "endpoint, so this calls the same undocumented sync endpoint "
            "app.ynab.com's web UI uses, authenticated with your browser session "
            "instead of a personal access token."
        ),
    )
    parser.add_argument(
        "--plan-id", help="YNAB plan ID. Required if you have more than one plan."
    )
    parser.add_argument(
        "--payee-ids",
        dest="payee_ids",
        action="append",
        help=(
            "Payee ID to delete. Repeat for multiple payees. If omitted, finds all "
            "unused payee IDs in the plan (unreferenced payees, transfer payees, and "
            "duplicate-named payees)."
        ),
    )
    parser.add_argument(
        "--for-real",
        action="store_true",
        help="Delete the payees instead of only previewing them.",
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
    parser.add_argument(
        "--sync",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh the SQLite DB before using it.",
    )
    return parser


async def _resolve_plan_id(con: aiosqlite.Connection, plan_id: str | None) -> str:
    async with con.execute("SELECT id, name FROM plans") as cur:
        rows = await cur.fetchall()
    plans = {str(row["id"]): str(row["name"]) for row in rows}
    if not plans:
        raise RuntimeError("No plans found in this YNAB account.")

    if plan_id:
        if plan_id not in plans:
            raise RuntimeError(f"No plan found with id '{plan_id}'.")
        return plan_id
    if len(plans) == 1:
        return next(iter(plans))

    names = ", ".join(f"{name} ({id_})" for id_, name in plans.items())
    raise RuntimeError(f"Found {len(plans)} plans - {names}. Specify --plan-id.")


async def _load_server_knowledge(con: aiosqlite.Connection, plan_id: str) -> int:
    async with con.execute(
        "SELECT last_knowledge_of_server FROM plans WHERE id = ?", (plan_id,)
    ) as cur:
        row = await cur.fetchone()

    if row is None or row["last_knowledge_of_server"] is None:
        raise RuntimeError(
            f"No last_knowledge_of_server recorded for plan '{plan_id}'. Run with "
            "--sync first."
        )

    return int(row["last_knowledge_of_server"])


async def _resolve_payees(
    con: aiosqlite.Connection, plan_id: str, payee_ids: Sequence[str]
) -> list[tuple[str, str]]:
    async with con.execute(
        "SELECT id, name FROM payees WHERE plan_id = ? AND NOT deleted", (plan_id,)
    ) as cur:
        rows = await cur.fetchall()

    names_by_id = {str(row["id"]): str(row["name"]) for row in rows}

    resolved: list[tuple[str, str]] = []
    missing: list[str] = []
    for payee_id in payee_ids:
        name = names_by_id.get(payee_id)
        if name is None:
            missing.append(payee_id)
            continue
        resolved.append((payee_id, name))

    if missing:
        raise RuntimeError(f"No payee found matching id(s): {', '.join(missing)}.")

    return resolved


async def _find_unused_payees(
    con: aiosqlite.Connection, plan_id: str
) -> list[tuple[str, str]]:
    async with con.execute(_UNUSED_PAYEES_QUERY, {"plan_id": plan_id}) as cur:
        rows = await cur.fetchall()

    return [(str(row["payee_id"]), str(row["payee_name"])) for row in rows]


async def delete_payees(
    *,
    plan_id: str | None,
    payee_ids: Sequence[str] | None,
    for_real: bool,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    token_override: str | None,
) -> int:
    token = resolve_token(token_override)

    if should_sync:
        print("** Refreshing SQLite DB **")
        await sync(token, db, full_refresh)
        print("** Done **")

    try:
        async with aiosqlite.connect(db) as con:
            con.row_factory = aiosqlite.Row
            resolved_plan_id = await _resolve_plan_id(con, plan_id)
            if payee_ids:
                resolved_payees = await _resolve_payees(
                    con, resolved_plan_id, payee_ids
                )
            else:
                resolved_payees = await _find_unused_payees(con, resolved_plan_id)
            server_knowledge = (
                await _load_server_knowledge(con, resolved_plan_id) if for_real else 0
            )
    except RuntimeError as err:
        print(err)
        return 1

    if not resolved_payees:
        print(f"No unused payees found in plan {resolved_plan_id}.")
        return 0

    print(f"Plan: {resolved_plan_id}")
    table = Table(title="Payees To Delete")
    table.add_column("ID")
    table.add_column("Payee")
    for payee_id, payee_name in resolved_payees:
        table.add_row(payee_id, payee_name)
    rich.print(table)

    if not for_real:
        print("Use --for-real to actually delete the payees.")
        return 0

    try:
        cookie = await resolve_session_cookie()
        session_token = resolve_session_token()
    except ValueError as err:
        print(err)
        return 1

    device_knowledge = 0
    async with aiohttp.ClientSession() as session:
        for payee_id, payee_name in resolved_payees:
            try:
                result = await delete_payee_entity(
                    session,
                    cookie=cookie,
                    session_token=session_token,
                    budget_version_id=resolved_plan_id,
                    payee_id=payee_id,
                    payee_name=payee_name,
                    starting_device_knowledge=device_knowledge,
                    ending_device_knowledge=device_knowledge + 1,
                    device_knowledge_of_server=server_knowledge,
                )
            except (aiohttp.ClientError, RuntimeError) as err:
                print(f"Failed to delete payee {payee_name!r}: {err}", file=sys.stderr)
                return 1
            device_knowledge += 1
            server_knowledge = result.get("current_server_knowledge", server_knowledge)
            print(f"Deleted payee {payee_name!r}.")

    return 0


async def run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    args = build_parser().parse_args(argv)
    return await delete_payees(
        plan_id=args.plan_id,
        payee_ids=args.payee_ids,
        for_real=args.for_real,
        db=args.sqlite_export_for_ynab_db,
        full_refresh=args.sqlite_export_for_ynab_full_refresh,
        should_sync=args.sync,
        token_override=token_override,
    )


__all__ = ["build_parser", "delete_payees", "run"]
