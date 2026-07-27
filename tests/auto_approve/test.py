import sqlite3
from typing import Any
from unittest.mock import call, patch

import aiosqlite
import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.auto_approve import (
    AutoApproveResult,
    Transaction,
    _transaction_from_row,
    auto_approve,
    fetch_auto_approve_transactions,
    run,
)

pytest_plugins = ("tests.auto_approve.fixtures",)


def unexpected_transactions_api(*args: object, **kwargs: object) -> None:
    raise AssertionError("TransactionsApi should not be constructed during dry-run")


def test_transaction_from_row_keeps_pair_without_json_import_payee_name():
    with sqlite3.connect(":memory:") as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            """
            SELECT
                'txn-1' AS id
                , 'plan-1' AS plan_id
                , 'Checking' AS account_name
                , 'Coffee' AS payee_name
                , '-$4.50' AS amount_formatted
                , '2026-04-20' AS date
                , 'cleared' AS cleared
                , 'not-json' AS import_payee_name
            """
        ).fetchone()

    txn = _transaction_from_row(row)

    assert txn == Transaction(
        id="txn-1",
        plan_id="plan-1",
        account_name="Checking",
        payee_name="Coffee",
        amount_formatted="-$4.50",
        date="2026-04-20",
        cleared="cleared",
    )


@pytest.mark.asyncio
async def test_fetch_auto_approve_transactions_filters_expected_rows(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_auto_approve_transactions(con)

    assert [txn.id for txn in found] == [
        "pair-a-1",
        "pair-a-2",
        "pair-b-1",
        "pair-b-2",
        "unmatched",
    ]
    assert [txn.should_delete for txn in found] == [
        False,
        True,
        True,
        False,
        False,
    ]
    assert [txn.cleared for txn in found] == [
        "cleared",
        "cleared",
        "uncleared",
        "uncleared",
        "cleared",
    ]


@patch.dict("os.environ", {_ENV_TOKEN: ""})
@pytest.mark.asyncio
async def test_run_requires_token(db):
    with pytest.raises(ValueError) as excinfo:
        await run(("--sqlite-export-for-ynab-db", str(db)))

    assert "Must set YNAB access token" in str(excinfo.value)


@pytest.mark.asyncio
@patch.dict("os.environ", {_ENV_TOKEN: ""})
async def test_auto_approve_requires_token(db):
    with pytest.raises(ValueError) as excinfo:
        await auto_approve(
            db=db,
            full_refresh=False,
            for_real=False,
            token_override=None,
            quiet=True,
        )

    assert "Must set YNAB access token" in str(excinfo.value)


def _expected_auto_approve_result(
    updated_count: int, cleared: int
) -> AutoApproveResult:
    return AutoApproveResult(
        transactions=[
            Transaction(
                id="pair-a-1",
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Coffee",
                amount_formatted="-$4.50",
                date="2026-04-20",
                cleared="cleared",
            ),
            Transaction(
                id="pair-a-2",
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Coffee",
                amount_formatted="-$4.50",
                date="2026-04-20",
                cleared="cleared",
                should_delete=True,
            ),
            Transaction(
                id="pair-b-1",
                plan_id="plan-2",
                account_name="Card",
                payee_name="Lunch",
                amount_formatted="-$12.00",
                date="2026-04-21",
                cleared="uncleared",
                should_delete=True,
            ),
            Transaction(
                id="pair-b-2",
                plan_id="plan-2",
                account_name="Card",
                payee_name="Lunch",
                amount_formatted="-$12.00",
                date="2026-04-21",
                cleared="uncleared",
            ),
            Transaction(
                id="unmatched",
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Solo",
                amount_formatted="-$7.00",
                date="2026-04-21",
                cleared="cleared",
            ),
        ],
        updated_count=updated_count,
        cleared=cleared,
    )


@patch("manager_for_ynab.auto_approve.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_auto_approve_uses_token_override(sync, db):
    result = await auto_approve(
        db=db,
        full_refresh=False,
        for_real=False,
        token_override="override-token",
        quiet=True,
    )

    sync.assert_called_once_with("override-token", db, False, quiet=True)
    assert result == _expected_auto_approve_result(updated_count=0, cleared=0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_auto_approve_quiet_suppresses_refresh_logs(sync, db, capsys):
    result = await auto_approve(
        db=db,
        full_refresh=False,
        for_real=False,
        token_override=None,
        quiet=True,
    )

    out, _ = capsys.readouterr()
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert out == ""
    assert result == _expected_auto_approve_result(updated_count=0, cleared=0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_auto_approve_for_real_returns_updated_count(
    sync, transactions_api, ynab_api_client, ynab_configuration, db
):
    updates: list[tuple[str, Any]] = []
    transactions_api.update_transactions.side_effect = lambda plan_id, wrapper: (
        updates.append((plan_id, wrapper))
    )

    result = await auto_approve(
        db=db,
        full_refresh=False,
        for_real=True,
        token_override=None,
        quiet=True,
    )

    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert [txn.id for txn in updates[0][1].transactions] == [
        "pair-a-1",
        "unmatched",
    ]
    assert [txn.id for txn in updates[1][1].transactions] == ["pair-b-2"]
    assert transactions_api.delete_transaction.call_args_list == [
        call("plan-1", "pair-a-2"),
        call("plan-2", "pair-b-1"),
    ]
    assert result == _expected_auto_approve_result(updated_count=5, cleared=2)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_auto_approve_for_real_skips_update_when_plan_only_deletes(
    sync, transactions_api, db
):
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE transactions SET import_payee_name = '{\"payee_name\": \"Lunch\"}' WHERE id = 'pair-b-2'"
        )

    updates: list[tuple[str, Any]] = []
    transactions_api.update_transactions.side_effect = lambda plan_id, wrapper: (
        updates.append((plan_id, wrapper))
    )

    result = await auto_approve(
        db=db,
        full_refresh=False,
        for_real=True,
        token_override=None,
        quiet=True,
    )

    sync.assert_called_once_with("token", db, False, quiet=True)
    assert [plan_id for plan_id, _ in updates] == ["plan-1"]
    assert transactions_api.delete_transaction.call_args_list == [
        call("plan-1", "pair-a-2"),
        call("plan-2", "pair-b-1"),
        call("plan-2", "pair-b-2"),
    ]
    assert result.updated_count == 5
    assert result.cleared == 2


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_dry_run_does_not_update_transactions(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 5 transaction(s) to update." in out
    assert "Transactions To Update" in out
    assert "Delete" in out
    assert "Update" in out
    assert "Use --for-real to actually update transactions." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_quiet_suppresses_all_output(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--quiet"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert out == ""


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_no_sync_uses_existing_db(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--no-sync"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    assert "** Refreshing SQLite DB **" not in out
    assert "Found 5 transaction(s) to update." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_no_matching_transactions(sync, db, capsys):
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE transactions SET approved = 1 WHERE matched_transaction_id IS NOT NULL OR id = 'unmatched'"
        )

    ret = await run(("--sqlite-export-for-ynab-db", str(db)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 0 transaction(s) to update." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_for_real_updates_transactions_grouped_by_plan(
    sync, transactions_api, ynab_api_client, ynab_configuration, db
):
    updates: list[tuple[str, Any]] = []
    transactions_api.update_transactions.side_effect = lambda plan_id, wrapper: (
        updates.append((plan_id, wrapper))
    )

    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--for-real"))

    assert ret == 0
    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert [txn.id for txn in updates[0][1].transactions] == [
        "pair-a-1",
        "unmatched",
    ]
    assert [txn.id for txn in updates[1][1].transactions] == ["pair-b-2"]
    assert transactions_api.delete_transaction.call_args_list == [
        call("plan-1", "pair-a-2"),
        call("plan-2", "pair-b-1"),
    ]
