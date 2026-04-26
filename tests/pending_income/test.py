import sqlite3
from datetime import date
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import aiosqlite
import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.pending_income import build_updates
from manager_for_ynab.pending_income import fetch_pending_income
from manager_for_ynab.pending_income import pending_income
from manager_for_ynab.pending_income import PendingIncomeResult
from manager_for_ynab.pending_income import run
from manager_for_ynab.pending_income import Transaction
from manager_for_ynab.pending_income import ynab


pytest_plugins = ("tests.pending_income.fixtures",)


def unexpected_transactions_api(*args: object, **kwargs: object) -> None:
    raise AssertionError("TransactionsApi should not be constructed during dry-run")


@pytest.mark.asyncio
async def test_fetch_pending_income_filters_expected_rows(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_pending_income(con)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["keep-1", "matched"],
        "plan-2": ["keep-2"],
    }


@pytest.mark.asyncio
async def test_fetch_pending_income_skip_matched_filters_matched_rows(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_pending_income(con, skip_matched=True)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["keep-1"],
        "plan-2": ["keep-2"],
    }


def test_build_updates_groups_by_plan():
    txns_by_plan = {
        "plan-1": [
            Transaction(
                "txn-1", "plan-1", "Checking", "Employer", "$100.00", "2026-04-01"
            )
        ],
        "plan-2": [
            Transaction(
                "txn-2", "plan-2", "Savings", "Employer", "$55.00", "2026-04-01"
            )
        ],
    }

    updates = build_updates(txns_by_plan, date(2026, 4, 14))

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in updates.items()} == {
        "plan-1": ["txn-1"],
        "plan-2": ["txn-2"],
    }
    assert all(
        txn.var_date == date(2026, 4, 14) for txns in updates.values() for txn in txns
    )


@patch.dict("os.environ", {_ENV_TOKEN: ""})
@pytest.mark.asyncio
async def test_run_requires_token(db):
    with pytest.raises(ValueError) as excinfo:
        await run(("--sqlite-export-for-ynab-db", str(db)))

    assert "Must set YNAB access token" in str(excinfo.value)


@pytest.mark.asyncio
@patch.dict("os.environ", {_ENV_TOKEN: ""})
async def test_pending_income_requires_token(db):
    with pytest.raises(ValueError) as excinfo:
        await pending_income(
            db=db,
            full_refresh=False,
            for_real=False,
            skip_matched=False,
            token_override=None,
            quiet=True,
        )

    assert "Must set YNAB access token" in str(excinfo.value)


def _expected_pending_income_result(
    updated_count: int,
    *,
    include_matched: bool = True,
) -> PendingIncomeResult:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    transactions = [
        Transaction(
            id="keep-1",
            plan_id="plan-1",
            account_name="Checking",
            payee_name="Employer",
            amount_formatted="$100.00",
            date=yesterday,
        ),
        Transaction(
            id="keep-2",
            plan_id="plan-2",
            account_name="Savings",
            payee_name="Employer",
            amount_formatted="$55.00",
            date=yesterday,
        ),
    ]
    if include_matched:
        transactions.insert(
            1,
            Transaction(
                id="matched",
                plan_id="plan-1",
                account_name="Checking",
                payee_name="Employer",
                amount_formatted="$65.00",
                date=yesterday,
            ),
        )
    return PendingIncomeResult(transactions=transactions, updated_count=updated_count)


@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_pending_income_uses_token_override(sync, db):
    result = await pending_income(
        db=db,
        full_refresh=False,
        for_real=False,
        skip_matched=False,
        token_override="override-token",
        quiet=True,
    )

    sync.assert_called_once_with("override-token", db, False, quiet=True)
    assert result == _expected_pending_income_result(0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_pending_income_skip_matched_excludes_matched_transactions(sync, db):
    result = await pending_income(
        db=db,
        full_refresh=False,
        for_real=False,
        skip_matched=True,
        token_override=None,
        quiet=True,
    )

    sync.assert_called_once_with("token", db, False, quiet=True)
    assert result == _expected_pending_income_result(0, include_matched=False)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_pending_income_quiet_suppresses_refresh_logs(sync, db, capsys):
    result = await pending_income(
        db=db,
        full_refresh=False,
        for_real=False,
        skip_matched=False,
        token_override=None,
        quiet=True,
    )

    out, _ = capsys.readouterr()
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert out == ""
    assert result == _expected_pending_income_result(0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_pending_income_for_real_returns_updated_count(
    sync, transactions_api, ynab_api_client, ynab_configuration, db
):
    updates: list[tuple[str, Any]] = []
    transactions_api.update_transactions.side_effect = lambda plan_id, wrapper: (
        updates.append((plan_id, wrapper))
    )

    result = await pending_income(
        db=db,
        full_refresh=False,
        for_real=True,
        skip_matched=False,
        token_override=None,
        quiet=True,
    )

    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert updates[0][1].transactions[0].id == "keep-1"
    assert [txn.id for txn in updates[0][1].transactions] == ["keep-1", "matched"]
    assert updates[1][1].transactions[0].id == "keep-2"
    assert result == _expected_pending_income_result(3)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_dry_run_does_not_update_transactions(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 3 income transaction(s) to update." in out
    assert "Use --for-real to actually update transactions." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_quiet_suppresses_all_output(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--quiet"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert out == ""


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_no_matching_transactions(sync, db, capsys):
    with sqlite3.connect(db) as con:
        con.execute("UPDATE transactions SET cleared = 'cleared'")

    ret = await run(("--sqlite-export-for-ynab-db", str(db)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 0 income transaction(s) to update." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.pending_income.sync")
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
    assert updates[0][1].transactions[0].id == "keep-1"
    assert [txn.id for txn in updates[0][1].transactions] == ["keep-1", "matched"]
    assert updates[1][1].transactions[0].id == "keep-2"


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_skip_matched_excludes_matched_transactions(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--skip-matched"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "Found 2 income transaction(s) to update." in out
    assert "matched" not in out.lower()
