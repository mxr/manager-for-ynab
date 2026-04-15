import sqlite3
from datetime import date
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import manager_for_ynab.pending_income as pending_income

if TYPE_CHECKING:
    from pathlib import Path


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
            INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        found = pending_income.fetch_pending_income(con.cursor())

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["keep-1"],
        "plan-2": ["keep-2"],
    }


def test_build_updates_groups_by_plan():
    txns_by_plan = {
        "plan-1": [
            pending_income.Transaction(
                "txn-1", "plan-1", "Checking", "Employer", "$100.00", "2026-04-01"
            )
        ],
        "plan-2": [
            pending_income.Transaction(
                "txn-2", "plan-2", "Savings", "Employer", "$55.00", "2026-04-01"
            )
        ],
    }

    updates = pending_income.build_updates(txns_by_plan, date(2026, 4, 14))

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in updates.items()} == {
        "plan-1": ["txn-1"],
        "plan-2": ["txn-2"],
    }
    assert all(
        txn.var_date == date(2026, 4, 14) for txns in updates.values() for txn in txns
    )


def test_main_requires_token(monkeypatch):
    monkeypatch.setenv(pending_income._ENV_TOKEN, "")

    with pytest.raises(ValueError) as excinfo:
        pending_income.run(())

    assert "Must set YNAB access token" in str(excinfo.value)


@patch("manager_for_ynab.pending_income.sync")
def test_main_dry_run_does_not_update_transactions(sync, monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)
    monkeypatch.setenv(pending_income._ENV_TOKEN, "token")

    def unexpected_transactions_api(*args, **kwargs):
        raise AssertionError("TransactionsApi should not be constructed during dry-run")

    monkeypatch.setattr(
        pending_income.ynab, "TransactionsApi", unexpected_transactions_api
    )

    ret = pending_income.run(("--sqlite-export-for-ynab-db", str(db_path)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once()
    assert "Found 2 income transaction(s) to update." in out
    assert "Use --for-real to actually update transactions." in out


@patch("manager_for_ynab.pending_income.sync")
def test_main_no_matching_transactions(sync, monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)
    monkeypatch.setenv(pending_income._ENV_TOKEN, "token")

    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE transactions SET cleared = 'cleared'")

    ret = pending_income.run(("--sqlite-export-for-ynab-db", str(db_path)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once()
    assert "Found 0 income transaction(s) to update." in out


@patch("manager_for_ynab.pending_income.sync")
def test_main_for_real_updates_transactions_grouped_by_plan(
    sync, monkeypatch, tmp_path
):
    db_path = tmp_path / "pending.sqlite"
    _create_pending_income_db(db_path)
    monkeypatch.setenv(pending_income._ENV_TOKEN, "token")

    updates: list[tuple[str, Any]] = []

    class FakeTransactionsApi:
        def __init__(self, client):
            self.client = client

        def update_transactions(self, plan_id, wrapper):
            updates.append((plan_id, wrapper))

    monkeypatch.setattr(pending_income.ynab, "TransactionsApi", FakeTransactionsApi)
    monkeypatch.setattr(
        pending_income.ynab, "ApiClient", lambda config: SimpleNamespace(config=config)
    )
    monkeypatch.setattr(
        pending_income.ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )

    ret = pending_income.run(
        ("--sqlite-export-for-ynab-db", str(db_path), "--for-real")
    )

    assert ret == 0
    sync.assert_called_once()
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert updates[0][1].transactions[0].id == "keep-1"
    assert updates[1][1].transactions[0].id == "keep-2"
