import sqlite3
from types import SimpleNamespace
from typing import Any
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.auto_approve import auto_approve
from manager_for_ynab.auto_approve import AutoApproveResult
from manager_for_ynab.auto_approve import build_updates
from manager_for_ynab.auto_approve import fetch_auto_approve_transactions
from manager_for_ynab.auto_approve import run
from manager_for_ynab.auto_approve import Transaction
from manager_for_ynab.auto_approve import ynab

if TYPE_CHECKING:
    from pathlib import Path


def _create_auto_approve_db(path: Path) -> None:
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
                , approved BOOLEAN
                , matched_transaction_id TEXT
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
                    "pair-a-1",
                    "plan-1",
                    "Checking",
                    "Coffee",
                    "-$4.50",
                    "2026-04-20",
                    0,
                    "pair-a-2",
                    0,
                ),
                (
                    "pair-a-2",
                    "plan-1",
                    "Checking",
                    "Coffee",
                    "-$4.50",
                    "2026-04-20",
                    0,
                    "pair-a-1",
                    0,
                ),
                (
                    "pair-b-1",
                    "plan-2",
                    "Card",
                    "Lunch",
                    "-$12.00",
                    "2026-04-21",
                    0,
                    "pair-b-2",
                    0,
                ),
                (
                    "pair-b-2",
                    "plan-2",
                    "Card",
                    "Lunch",
                    "-$12.00",
                    "2026-04-21",
                    0,
                    "pair-b-1",
                    0,
                ),
                (
                    "approved-1",
                    "plan-1",
                    "Checking",
                    "Done",
                    "-$3.00",
                    "2026-04-21",
                    1,
                    "approved-2",
                    0,
                ),
                (
                    "approved-2",
                    "plan-1",
                    "Checking",
                    "Done",
                    "-$3.00",
                    "2026-04-21",
                    0,
                    "approved-1",
                    0,
                ),
                (
                    "unmatched",
                    "plan-1",
                    "Checking",
                    "Solo",
                    "-$7.00",
                    "2026-04-21",
                    0,
                    None,
                    0,
                ),
                (
                    "deleted-1",
                    "plan-1",
                    "Checking",
                    "Gone",
                    "-$5.00",
                    "2026-04-21",
                    0,
                    "deleted-2",
                    1,
                ),
                (
                    "deleted-2",
                    "plan-1",
                    "Checking",
                    "Gone",
                    "-$5.00",
                    "2026-04-21",
                    0,
                    "deleted-1",
                    0,
                ),
            ),
        )


def test_fetch_auto_approve_transactions_filters_expected_rows(tmp_path):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        found = fetch_auto_approve_transactions(con.cursor())

    assert {plan_id: [txn.id for txn in txns] for plan_id, txns in found.items()} == {
        "plan-1": ["pair-a-1"],
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


@pytest.mark.parametrize("func", (lambda: run(()), lambda: auto_approve()))
def test_requires_token(monkeypatch, func):
    monkeypatch.setenv(_ENV_TOKEN, "")

    with pytest.raises(ValueError) as excinfo:
        func()

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


@patch("manager_for_ynab.auto_approve.sync")
def test_auto_approve_uses_token_override(sync, monkeypatch, tmp_path):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.delenv(_ENV_TOKEN, raising=False)

    def unexpected_transactions_api(*args, **kwargs):
        raise AssertionError("TransactionsApi should not be constructed during dry-run")

    monkeypatch.setattr(ynab, "TransactionsApi", unexpected_transactions_api)

    result = auto_approve(db=db_path, token_override="override-token")

    sync.assert_called_once_with("override-token", db_path, False, quiet=True)
    assert result == _expected_auto_approve_result(0)


@patch("manager_for_ynab.auto_approve.sync")
def test_auto_approve_quiet_suppresses_refresh_logs(
    sync, monkeypatch, tmp_path, capsys
):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.setenv(_ENV_TOKEN, "token")

    def unexpected_transactions_api(*args, **kwargs):
        raise AssertionError("TransactionsApi should not be constructed during dry-run")

    monkeypatch.setattr(ynab, "TransactionsApi", unexpected_transactions_api)

    result = auto_approve(db=db_path)

    out, _ = capsys.readouterr()
    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert out == ""
    assert result == _expected_auto_approve_result(0)


@patch("manager_for_ynab.auto_approve.sync")
def test_auto_approve_for_real_returns_updated_count(sync, monkeypatch, tmp_path):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.setenv(_ENV_TOKEN, "token")

    updates: list[tuple[str, Any]] = []

    class FakeTransactionsApi:
        def __init__(self, client):
            self.client = client

        def update_transactions(self, plan_id, wrapper):
            updates.append((plan_id, wrapper))

    monkeypatch.setattr(ynab, "TransactionsApi", FakeTransactionsApi)
    monkeypatch.setattr(
        ynab, "ApiClient", lambda config: SimpleNamespace(config=config)
    )
    monkeypatch.setattr(
        ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )

    result = auto_approve(db=db_path, for_real=True)

    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert [txn.id for txn in updates[0][1].transactions] == ["pair-a-1", "pair-a-2"]
    assert [txn.id for txn in updates[1][1].transactions] == ["pair-b-1", "pair-b-2"]
    assert result == _expected_auto_approve_result(2)


@patch("manager_for_ynab.auto_approve.sync")
def test_run_dry_run_does_not_update_transactions(sync, monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.setenv(_ENV_TOKEN, "token")

    def unexpected_transactions_api(*args, **kwargs):
        raise AssertionError("TransactionsApi should not be constructed during dry-run")

    monkeypatch.setattr(ynab, "TransactionsApi", unexpected_transactions_api)

    ret = run(("--sqlite-export-for-ynab-db", str(db_path)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 2 matched transaction(s) to approve." in out
    assert "Use --for-real to actually approve transactions." in out


@patch("manager_for_ynab.auto_approve.sync")
def test_run_quiet_suppresses_all_output(sync, monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.setenv(_ENV_TOKEN, "token")

    def unexpected_transactions_api(*args, **kwargs):
        raise AssertionError("TransactionsApi should not be constructed during dry-run")

    monkeypatch.setattr(ynab, "TransactionsApi", unexpected_transactions_api)

    ret = run(("--sqlite-export-for-ynab-db", str(db_path), "--quiet"))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=True)
    assert out == ""


@patch("manager_for_ynab.auto_approve.sync")
def test_run_no_matching_transactions(sync, monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.setenv(_ENV_TOKEN, "token")

    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE transactions SET approved = 1 WHERE matched_transaction_id IS NOT NULL"
        )

    ret = run(("--sqlite-export-for-ynab-db", str(db_path)))

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out
    assert "Found 0 matched transaction(s) to approve." in out


@patch("manager_for_ynab.auto_approve.sync")
def test_run_for_real_updates_transactions_grouped_by_plan(sync, monkeypatch, tmp_path):
    db_path = tmp_path / "auto-approve.sqlite"
    _create_auto_approve_db(db_path)
    monkeypatch.setenv(_ENV_TOKEN, "token")

    updates: list[tuple[str, Any]] = []

    class FakeTransactionsApi:
        def __init__(self, client):
            self.client = client

        def update_transactions(self, plan_id, wrapper):
            updates.append((plan_id, wrapper))

    monkeypatch.setattr(ynab, "TransactionsApi", FakeTransactionsApi)
    monkeypatch.setattr(
        ynab, "ApiClient", lambda config: SimpleNamespace(config=config)
    )
    monkeypatch.setattr(
        ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )

    ret = run(("--sqlite-export-for-ynab-db", str(db_path), "--for-real"))

    assert ret == 0
    sync.assert_called_once_with("token", db_path, False, quiet=False)
    assert [plan_id for plan_id, _ in updates] == ["plan-1", "plan-2"]
    assert [txn.id for txn in updates[0][1].transactions] == ["pair-a-1", "pair-a-2"]
    assert [txn.id for txn in updates[1][1].transactions] == ["pair-b-1", "pair-b-2"]
