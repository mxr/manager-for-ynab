import sqlite3
from typing import Any
from unittest.mock import patch

import aiosqlite
import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.auto_approve import auto_approve
from manager_for_ynab.auto_approve import AutoApproveResult
from manager_for_ynab.auto_approve import build_updates
from manager_for_ynab.auto_approve import fetch_auto_approve_transactions
from manager_for_ynab.auto_approve import run
from manager_for_ynab.auto_approve import Transaction
from manager_for_ynab.auto_approve import ynab


pytest_plugins = ("tests.auto_approve.fixtures",)


def unexpected_transactions_api(*args: object, **kwargs: object) -> None:
    raise AssertionError("TransactionsApi should not be constructed during dry-run")


@pytest.mark.asyncio
async def test_fetch_auto_approve_transactions_filters_expected_rows(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_auto_approve_transactions(con)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["pair-a-1", "unmatched"],
        "plan-2": ["pair-b-1"],
    }


def test_build_updates_groups_by_plan_and_updates_both_ids():
    txns_by_plan = {
        "plan-1": [
            Transaction(
                id="txn-1",
                matched_transaction_id="txn-2",
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Coffee",
                amount_formatted="-$4.50",
                date="2026-04-20",
            )
        ],
        "plan-2": [
            Transaction(
                id="txn-3",
                matched_transaction_id="txn-4",
                plan_id="plan-2",
                account_name="Card",
                payee_name="Lunch",
                amount_formatted="-$12.00",
                date="2026-04-21",
            )
        ],
    }

    updates = build_updates(txns_by_plan)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in updates.items()} == {
        "plan-1": ["txn-1", "txn-2"],
        "plan-2": ["txn-3", "txn-4"],
    }
    assert all(txn.approved is True for txns in updates.values() for txn in txns)


def test_build_updates_approves_unmatched_scheduled_transactions():
    txns_by_plan = {
        "plan-1": [
            Transaction(
                id="txn-1",
                matched_transaction_id=None,
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Apple",
                amount_formatted="-$21.76",
                date="2026-04-20",
            )
        ]
    }

    updates = build_updates(txns_by_plan)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in updates.items()} == {
        "plan-1": ["txn-1"],
    }


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


def _expected_auto_approve_result(updated_count: int) -> AutoApproveResult:
    return AutoApproveResult(
        transactions=[
            Transaction(
                id="pair-a-1",
                matched_transaction_id="pair-a-2",
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Coffee",
                amount_formatted="-$4.50",
                date="2026-04-20",
            ),
            Transaction(
                id="unmatched",
                matched_transaction_id=None,
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Solo",
                amount_formatted="-$7.00",
                date="2026-04-21",
            ),
            Transaction(
                id="pair-b-1",
                matched_transaction_id="pair-b-2",
                plan_id="plan-2",
                account_name="Card",
                payee_name="Lunch",
                amount_formatted="-$12.00",
                date="2026-04-21",
            ),
        ],
        updated_count=updated_count,
    )


@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
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
    assert result == _expected_auto_approve_result(0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
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
    assert result == _expected_auto_approve_result(0)


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
        "pair-a-2",
        "unmatched",
    ]
    assert [txn.id for txn in updates[1][1].transactions] == ["pair-b-1", "pair-b-2"]
    assert result == _expected_auto_approve_result(3)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_dry_run_does_not_update_transactions(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 3 transaction(s) to approve." in out
    assert "Use --for-real to actually approve transactions." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_quiet_suppresses_all_output(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--quiet"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert out == ""


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.auto_approve.sync")
@pytest.mark.asyncio
async def test_run_no_sync_uses_existing_db(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--no-sync"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    assert "** Refreshing SQLite DB **" not in out
    assert "Found 3 transaction(s) to approve." in out


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
    assert "Found 0 transaction(s) to approve." in out


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
        "pair-a-2",
        "unmatched",
    ]
    assert [txn.id for txn in updates[1][1].transactions] == ["pair-b-1", "pair-b-2"]
