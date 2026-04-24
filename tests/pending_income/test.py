import sqlite3
from datetime import date
from datetime import timedelta
from typing import Any
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.pending_income import build_updates
from manager_for_ynab.pending_income import fetch_pending_income
from manager_for_ynab.pending_income import pending_income
from manager_for_ynab.pending_income import PendingIncomeResult
from manager_for_ynab.pending_income import run
from manager_for_ynab.pending_income import Transaction
from manager_for_ynab.pending_income import ynab

if TYPE_CHECKING:
    from pathlib import Path


class FakeConfiguration:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token


class FakeApiClient:
    def __init__(self, config: FakeConfiguration) -> None:
        self.config = config


def unexpected_transactions_api(*args: object, **kwargs: object) -> None:
    raise AssertionError("TransactionsApi should not be constructed during dry-run")


def _create_pending_income_db(path: Path) -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY
                , plan_id TEXT
                , account_name TEXT
                , payee_name TEXT
                , amount_formatted TEXT
                , date TEXT
                , cleared TEXT
                , amount INT
                , matched_transaction_id TEXT
                , deleted BOOLEAN
            );

            CREATE TABLE subtransactions (
                transfer_transaction_id TEXT
                , deleted BOOLEAN
            );
            """
        )
        con.executemany(
            """
            INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "keep-1",
                    "plan-1",
                    "Checking",
                    "Employer",
                    "$100.00",
                    yesterday.isoformat(),
                    "uncleared",
                    100000,
                    None,
                    0,
                ),
                (
                    "keep-2",
                    "plan-2",
                    "Savings",
                    "Employer",
                    "$55.00",
                    yesterday.isoformat(),
                    "uncleared",
                    55000,
                    None,
                    0,
                ),
                (
                    "future",
                    "plan-1",
                    "Checking",
                    "Future",
                    "$50.00",
                    tomorrow.isoformat(),
                    "uncleared",
                    50000,
                    None,
                    0,
                ),
                (
                    "negative",
                    "plan-1",
                    "Checking",
                    "Refund",
                    "-$20.00",
                    yesterday.isoformat(),
                    "uncleared",
                    -20000,
                    None,
                    0,
                ),
                (
                    "cleared",
                    "plan-1",
                    "Checking",
                    "Cleared",
                    "$10.00",
                    yesterday.isoformat(),
                    "cleared",
                    10000,
                    None,
                    0,
                ),
                (
                    "prior-month",
                    "plan-1",
                    "Checking",
                    "Old",
                    "$30.00",
                    last_month.isoformat(),
                    "uncleared",
                    30000,
                    None,
                    0,
                ),
                (
                    "transfer",
                    "plan-1",
                    "Checking",
                    "Transfer",
                    "$40.00",
                    yesterday.isoformat(),
                    "uncleared",
                    40000,
                    None,
                    0,
                ),
                (
                    "matched",
                    "plan-1",
                    "Checking",
                    "Employer",
                    "$65.00",
                    yesterday.isoformat(),
                    "uncleared",
                    65000,
                    "matched-peer",
                    0,
                ),
            ),
        )
        con.execute("INSERT INTO subtransactions VALUES (?, ?)", ("transfer", 0))


def test_fetch_pending_income_filters_expected_rows(tmp_path):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        found = fetch_pending_income(con.cursor())

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["keep-1", "matched"],
        "plan-2": ["keep-2"],
    }


def test_fetch_pending_income_skip_matched_filters_matched_rows(tmp_path):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        found = fetch_pending_income(con.cursor(), skip_matched=True)

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


@pytest.mark.parametrize("func", (lambda: run(()), lambda: pending_income()))
@patch.dict("os.environ", {_ENV_TOKEN: ""})
def test_requires_token(func):
    with pytest.raises(ValueError) as excinfo:
        func()

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


@patch.dict("os.environ", {}, clear=True)
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
def test_pending_income_uses_token_override(sync, tmp_path):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    result = pending_income(db=db_path, token_override="override-token")

    sync.assert_called_once_with("override-token", db_path, False, quiet=True)
    assert result == _expected_pending_income_result(0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
def test_pending_income_skip_matched_excludes_matched_transactions(sync, tmp_path):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    result = pending_income(db=db_path, skip_matched=True)

    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert result == _expected_pending_income_result(0, include_matched=False)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
def test_pending_income_quiet_suppresses_refresh_logs(sync, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    result = pending_income(db=db_path)

    out, _ = capsys.readouterr()
    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert out == ""
    assert result == _expected_pending_income_result(0)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "Configuration", FakeConfiguration)
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "TransactionsApi")
@patch("manager_for_ynab.pending_income.sync")
def test_pending_income_for_real_returns_updated_count(
    sync, transactions_api, tmp_path
):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    updates: list[tuple[str, Any]] = []

    class FakeTransactionsApi:
        def __init__(self, client):
            self.client = client

        def update_transactions(self, plan_id, wrapper):
            updates.append((plan_id, wrapper))

    transactions_api.side_effect = FakeTransactionsApi

    result = pending_income(db=db_path, for_real=True)

    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert updates[0][1].transactions[0].id == "keep-1"
    assert [txn.id for txn in updates[0][1].transactions] == ["keep-1", "matched"]
    assert updates[1][1].transactions[0].id == "keep-2"
    assert result == _expected_pending_income_result(3)


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
def test_run_dry_run_does_not_update_transactions(sync, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    ret = run(("--sqlite-export-for-ynab-db", str(db_path)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 3 income transaction(s) to update." in out
    assert "Use --for-real to actually update transactions." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
def test_run_quiet_suppresses_all_output(sync, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    ret = run(("--sqlite-export-for-ynab-db", str(db_path), "--quiet"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert out == ""


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.pending_income.sync")
def test_run_no_matching_transactions(sync, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE transactions SET cleared = 'cleared'")

    ret = run(("--sqlite-export-for-ynab-db", str(db_path)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 0 income transaction(s) to update." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "Configuration", FakeConfiguration)
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "TransactionsApi")
@patch("manager_for_ynab.pending_income.sync")
def test_run_for_real_updates_transactions_grouped_by_plan(
    sync, transactions_api, tmp_path
):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    updates: list[tuple[str, Any]] = []

    class FakeTransactionsApi:
        def __init__(self, client):
            self.client = client

        def update_transactions(self, plan_id, wrapper):
            updates.append((plan_id, wrapper))

    transactions_api.side_effect = FakeTransactionsApi

    ret = run(("--sqlite-export-for-ynab-db", str(db_path), "--for-real"))

    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert updates[0][1].transactions[0].id == "keep-1"
    assert [txn.id for txn in updates[0][1].transactions] == ["keep-1", "matched"]
    assert updates[1][1].transactions[0].id == "keep-2"


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(ynab, "TransactionsApi", unexpected_transactions_api)
@patch("manager_for_ynab.pending_income.sync")
def test_run_skip_matched_excludes_matched_transactions(sync, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)

    ret = run(("--sqlite-export-for-ynab-db", str(db_path), "--skip-matched"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert "Found 2 income transaction(s) to update." in out
    assert "matched" not in out.lower()
