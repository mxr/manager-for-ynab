import json
import re
import sqlite3
from unittest.mock import patch

import pytest

from manager_for_ynab.reconciler import _ENV_TOKEN
from manager_for_ynab.reconciler import _row_factory
from manager_for_ynab.reconciler import do_reconcile
from manager_for_ynab.reconciler import fetch_plan_accts
from manager_for_ynab.reconciler import fetch_transactions
from manager_for_ynab.reconciler import run
from manager_for_ynab.reconciler import YnabClient
from testing.fixtures import db
from testing.fixtures import mock_aioresponses
from testing.fixtures import PLAN_ID
from testing.fixtures import TOKEN


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.parametrize(
    ("target", "expected", "substr"),
    (
        pytest.param(
            500,
            0,
            "[Checking] *    -$60.00 - Payee",
            id="reconciles cleared and uncleared",
        ),
        pytest.param(
            430, 0, "[Checking] *    -$30.00 - Payee", id="reconciles only cleared"
        ),
        pytest.param(
            600, 1, "[Checking] No match found for target -$600.00", id="no match"
        ),
    ),
)
def test_main(sync, db, monkeypatch, capsys, target, expected, substr):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = run(
        (
            "--account-name-regex",
            "Checking",
            "--target",
            str(target),
            "--sqlite-export-for-ynab-db",
            db,
        )
    )
    out, _ = capsys.readouterr()
    sync.assert_called()
    assert ret == expected
    assert substr in out


@patch("manager_for_ynab.reconciler.sync")
def test_main_nothing_to_do(sync, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE transactions SET cleared = 'uncleared' where cleared = 'cleared'"
        )

    ret = run(
        (
            "--account-name-regex",
            "Checking",
            "--target",
            "430",
            "--sqlite-export-for-ynab-db",
            db,
        )
    )
    sync.assert_called()
    assert ret == 0


@patch("manager_for_ynab.reconciler.sync")
@patch.object(YnabClient, "reconcile")
@pytest.mark.usefixtures(db.__name__)
def test_main_reconciles_with_for_real(sync, reconcile, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = run(
        (
            "--account-name-regex",
            "Checking",
            "--target",
            "500",
            "--sqlite-export-for-ynab-db",
            db,
            "--for-real",
        )
    )
    sync.assert_called()
    assert ret == 0
    reconcile.assert_called()


def test_main_no_token(monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, "")

    with pytest.raises(ValueError) as excinfo:
        run(("--account-name-regex", "checking.+123", "--target", "410.50"))

    assert "Must set YNAB access token" in str(excinfo.value)


def test_main_mode_single_requires_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        run(())

    assert "--mode single" in str(excinfo.value)


def test_main_mode_single_rejects_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        run(("--account-target-pairs", "Checking=500"))

    assert "--account-target-pairs" in str(excinfo.value)


def test_main_mode_batch_requires_account_target_pairs():
    with pytest.raises(ValueError) as excinfo:
        run(("--mode", "batch"))

    assert "--account-target-pairs" in str(excinfo.value)


def test_main_mode_batch_rejects_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        run(("--mode", "batch", "--account-name-regex", "Checking", "--target", "500"))

    assert "--mode batch" in str(excinfo.value)


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
def test_main_mode_batch(sync, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)
    with sqlite3.connect(db) as con:
        con.execute(
            """
            UPDATE transactions
            SET cleared = 'reconciled'
            WHERE account_id = (SELECT id FROM accounts WHERE name = 'Checking')
            """
        )

    ret = run(
        (
            "--mode",
            "batch",
            "--account-target-pairs",
            "Checking=430",
            "Credit=290",
            "--sqlite-export-for-ynab-db",
            db,
        )
    )

    sync.assert_called()
    assert ret == 0


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
def test_main_mode_batch_preserves_pair_order(sync, db, monkeypatch, capsys):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)
    with sqlite3.connect(db) as con:
        con.execute(
            """
            UPDATE transactions
            SET cleared = 'uncleared'
            WHERE account_id IN (
                SELECT id FROM accounts WHERE name IN ('Checking', 'Credit Card')
            )
            AND cleared != 'reconciled'
            """
        )

    ret = run(
        (
            "--mode",
            "batch",
            "--account-target-pairs",
            "Credit=200",
            "Checking=430",
            "--sqlite-export-for-ynab-db",
            db,
        )
    )

    out, _ = capsys.readouterr()
    sync.assert_called()
    assert ret == 0
    assert "[Checking] Balance already reconciled to target" in out
    assert "[Credit Card] Balance already reconciled to target" in out


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.parametrize(
    ("regex", "substr"),
    (
        pytest.param("c", "My Plan", id="more than 1"),
        pytest.param("foo", "nothing!", id="none"),
    ),
)
def test_main_not_one_account(sync, db, monkeypatch, regex, substr):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    with pytest.raises(ValueError) as excinfo:
        run(
            (
                "--account-name-regex",
                regex,
                "--target",
                "500",
                "--sqlite-export-for-ynab-db",
                db,
            )
        )

    assert "Must have 1 total account matches" in str(excinfo.value)
    assert substr in str(excinfo.value)


@pytest.mark.asyncio
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_main_do_reconcile(sync, db, mock_aioresponses):
    with sqlite3.connect(db) as con:
        con.create_function(
            "REGEXP", 2, lambda x, y: bool(re.search(y, x, re.IGNORECASE))
        )
        con.row_factory = _row_factory

        cur = con.cursor()

        transactions = fetch_transactions(cur, fetch_plan_accts(cur, ["checking"]))[0]

    mock_aioresponses.patch(
        re.compile("https://api.ynab.com/v1/plans/.+/transactions"),
        body=json.dumps(
            {
                "data": {
                    "transactions": [
                        {"id": t.id, "cleared": "reconciled"} for t in transactions
                    ]
                }
            }
        ),
    )

    await do_reconcile(TOKEN, PLAN_ID, transactions, "Reconciling")


@pytest.mark.asyncio
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_main_do_reconcile_error_4034(sync, db, mock_aioresponses):
    with sqlite3.connect(db) as con:
        con.create_function(
            "REGEXP", 2, lambda x, y: bool(re.search(y, x, re.IGNORECASE))
        )
        con.row_factory = _row_factory

        cur = con.cursor()

        transactions = fetch_transactions(cur, fetch_plan_accts(cur, ["checking"]))[0]

    mock_aioresponses.patch(
        re.compile("https://api.ynab.com/v1/plans/.+/transactions"),
        body=json.dumps(
            {
                "data": {
                    "transactions": [
                        {"id": t.id, "cleared": "reconciled"} for t in transactions
                    ]
                }
            }
        ),
        payload={"error": {"id": "403.4"}},
    )

    for t in transactions:
        mock_aioresponses.patch(
            re.compile("https://api.ynab.com/v1/plans/.+/transactions"),
            body=json.dumps(
                {"data": {"transactions": [{"id": t.id, "cleared": "reconciled"}]}}
            ),
        )

    await do_reconcile(TOKEN, PLAN_ID, transactions, "Reconciling")
