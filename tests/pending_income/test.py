import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from unittest.mock import patch

import aiosqlite
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from manager_for_ynab.pending_income import PendingIncomeResult
from manager_for_ynab.pending_income import SubTransaction
from manager_for_ynab.pending_income import build_split_recreations
from manager_for_ynab.pending_income import build_updates
from manager_for_ynab.pending_income import fetch_pending_income
from manager_for_ynab.pending_income import pending_income
from manager_for_ynab.pending_income import run
from testing.fixtures import CHECKING_ACCOUNT_ID
from testing.fixtures import DINING_OUT_CATEGORY_ID
from testing.fixtures import EMPLOYER_PAYEE_ID

pytest_plugins = ("tests.pending_income.fixtures",)


def unexpected_transactions_api(*args: object, **kwargs: object) -> None:
    raise AssertionError("TransactionsApi should not be constructed during dry-run")


@pytest.mark.asyncio
async def test_fetch_pending_income_filters_expected_rows(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_pending_income(con)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["keep-1", "matched", "split"],
        "plan-2": ["keep-2"],
    }


@pytest.mark.asyncio
async def test_fetch_pending_income_excludes_transfer_mirror_of_split(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_pending_income(con)

    ids = [txn.id for txns in found.values() for txn in txns]
    assert "transfer-mirror-of-split" not in ids


@pytest.mark.asyncio
async def test_fetch_pending_income_marks_split_transactions(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_pending_income(con)

    split = next(txn for txn in found["plan-1"] if txn.id == "split")
    assert split.is_split
    assert split.subtransactions == (
        SubTransaction(
            amount=25000,
            payee_id=EMPLOYER_PAYEE_ID,
            payee_name="Employer",
            category_id=DINING_OUT_CATEGORY_ID,
            memo="half",
        ),
        SubTransaction(
            amount=15000,
            payee_id=None,
            payee_name=None,
            category_id=None,
            memo="other half",
        ),
    )

    keep_1 = next(txn for txn in found["plan-1"] if txn.id == "keep-1")
    assert not keep_1.is_split
    assert keep_1.subtransactions == ()


@pytest.mark.asyncio
async def test_fetch_pending_income_skip_matched_filters_matched_rows(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        found = await fetch_pending_income(con, skip_matched=True)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["keep-1", "split"],
        "plan-2": ["keep-2"],
    }


@pytest.mark.asyncio
async def test_build_updates_excludes_split_transactions(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        txns_by_plan = await fetch_pending_income(con)

    today = datetime.now().astimezone().date()
    updates = build_updates(txns_by_plan, today)

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in updates.items()} == {
        "plan-1": ["keep-1", "matched"],
        "plan-2": ["keep-2"],
    }
    assert all(txn.var_date == today for txns in updates.values() for txn in txns)


@pytest.mark.asyncio
async def test_build_split_recreations_only_includes_split_transactions(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        txns_by_plan = await fetch_pending_income(con)

    today = datetime.now().astimezone().date()
    recreations = build_split_recreations(txns_by_plan, today)

    assert list(recreations) == ["plan-1"]
    [(transaction_id, new_txn)] = recreations["plan-1"]
    assert transaction_id == "split"
    assert str(new_txn.account_id) == CHECKING_ACCOUNT_ID
    assert new_txn.var_date == today
    assert new_txn.amount == 40000
    assert new_txn.subtransactions is not None
    [first_subtxn, second_subtxn] = new_txn.subtransactions
    assert first_subtxn.amount == 25000
    assert str(first_subtxn.payee_id) == EMPLOYER_PAYEE_ID
    assert str(first_subtxn.category_id) == DINING_OUT_CATEGORY_ID
    assert first_subtxn.memo == "half"
    assert second_subtxn.amount == 15000
    assert second_subtxn.payee_id is None
    assert second_subtxn.category_id is None
    assert second_subtxn.memo == "other half"


@pytest.mark.token_env("")
@pytest.mark.asyncio
async def test_run_requires_token(db):
    with pytest.raises(ValueError) as excinfo:
        await run(("--sqlite-export-for-ynab-db", str(db)))

    assert "Must set YNAB access token" in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.token_env("")
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


async def _expected_pending_income_result(
    db: Path,
    updated_count: int,
    *,
    skip_matched: bool = False,
) -> PendingIncomeResult:
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        txns_by_plan = await fetch_pending_income(con, skip_matched=skip_matched)

    transactions = [txn for txns in txns_by_plan.values() for txn in txns]
    return PendingIncomeResult(transactions=transactions, updated_count=updated_count)


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
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
    assert result == await _expected_pending_income_result(db, 0)


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
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
    assert result == await _expected_pending_income_result(db, 0, skip_matched=True)


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
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
    assert result == await _expected_pending_income_result(db, 0)


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
    assert [txn.id for txn in updates[0][1].transactions] == ["keep-1", "matched"]
    assert updates[1][1].transactions[0].id == "keep-2"
    transactions_api.delete_transaction.assert_called_once_with("plan-1", "split")
    transactions_api.create_transaction.assert_called_once()
    assert result == await _expected_pending_income_result(db, 4)


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_dry_run_does_not_update_transactions(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 4 income transaction(s) to update." in out
    assert "Use --for-real to actually update transactions." in out


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_quiet_suppresses_all_output(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--quiet"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=True)
    assert out == ""


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_no_sync_uses_existing_db(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--no-sync"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    assert "** Refreshing SQLite DB **" not in out
    assert "Found 4 income transaction(s) to update." in out


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
    assert [txn.id for txn in updates[0][1].transactions] == ["keep-1", "matched"]
    assert updates[1][1].transactions[0].id == "keep-2"
    transactions_api.delete_transaction.assert_called_once_with("plan-1", "split")
    transactions_api.create_transaction.assert_called_once()


@patch("manager_for_ynab.pending_income.TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
@pytest.mark.asyncio
async def test_run_skip_matched_excludes_matched_transactions(sync, db, capsys):
    ret = await run(("--sqlite-export-for-ynab-db", str(db), "--skip-matched"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    assert "Found 3 income transaction(s) to update." in out
    assert "matched" not in out.lower()
