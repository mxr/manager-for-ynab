import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import aiosqlite
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token
from manager_for_ynab._browser_session import resolve_session_cookie
from manager_for_ynab._browser_session import resolve_session_token
from manager_for_ynab._ynab_sync_api import delete_payee as delete_payee_entity

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab delete-payees"


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
        "--payee-name",
        dest="payee_names",
        action="append",
        required=True,
        help="Exact payee name to delete (case-insensitive). Repeat for multiple payees.",
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
    con: aiosqlite.Connection, plan_id: str, payee_names: Sequence[str]
) -> list[tuple[str, str]]:
    async with con.execute(
        "SELECT id, name FROM payees WHERE plan_id = ? AND NOT deleted AND name IS NOT NULL",
        (plan_id,),
    ) as cur:
        rows = await cur.fetchall()

    by_lower_name: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        by_lower_name.setdefault(str(row["name"]).lower(), []).append(
            (str(row["id"]), str(row["name"]))
        )

    resolved: list[tuple[str, str]] = []
    missing: list[str] = []
    for payee_name in payee_names:
        matches = by_lower_name.get(payee_name.lower())
        if not matches:
            missing.append(payee_name)
            continue
        resolved.extend(matches)

    if missing:
        raise RuntimeError(f"No payee found matching name(s): {', '.join(missing)}.")
    return resolved


async def delete_payees(
    *,
    plan_id: str | None,
    payee_names: Sequence[str],
    for_real: bool,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    token_override: str | None,
    cookie_override: str | None = None,
    session_token_override: str | None = None,
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
            resolved_payees = await _resolve_payees(con, resolved_plan_id, payee_names)
            server_knowledge = (
                await _load_server_knowledge(con, resolved_plan_id) if for_real else 0
            )
    except RuntimeError as err:
        print(err)
        return 1

    names = ", ".join(f"{name!r}" for _, name in resolved_payees)
    print(f"Targeting payees {names} in plan {resolved_plan_id}")

    if not for_real:
        print("Use --for-real to actually delete the payees.")
        return 0

    try:
        cookie = resolve_session_cookie(cookie_override)
        session_token = resolve_session_token(session_token_override)
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
        payee_names=args.payee_names,
        for_real=args.for_real,
        db=args.sqlite_export_for_ynab_db,
        full_refresh=args.sqlite_export_for_ynab_full_refresh,
        should_sync=args.sync,
        token_override=token_override,
    )


__all__ = ["build_parser", "delete_payees", "run"]
