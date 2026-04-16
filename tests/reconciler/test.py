import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.reconciler import _parse_account_targets
from manager_for_ynab.reconciler import build_parser
from manager_for_ynab.reconciler import do_reconcile
from manager_for_ynab.reconciler import fetch_plan_accts
from manager_for_ynab.reconciler import fetch_transactions
from manager_for_ynab.reconciler import run
from manager_for_ynab.reconciler import YnabClient
from testing.fixtures import db
from testing.fixtures import mock_aioresponses
from testing.fixtures import PLAN_ID
from testing.fixtures import TOKEN


def _build_parser_with_raw_target():
    parser = build_parser()
    for action in parser._actions:
        if action.dest == "target":
            action.type = str
            break
    return parser


def _run(argv, *, token_override=None):
    with patch(
        "manager_for_ynab.reconciler.build_parser",
        side_effect=_build_parser_with_raw_target,
    ):
        return run(argv, token_override=token_override)


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
def test_run(sync, db, monkeypatch, capsys, target, expected, substr):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = _run(
        (
            "--account-like",
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
def test_run_nothing_to_do(sync, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE transactions SET cleared = 'uncleared' where cleared = 'cleared'"
        )

    ret = _run(
        (
            "--account-like",
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
def test_run_reconciles_with_for_real(sync, reconcile, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = _run(
        (
            "--account-like",
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


def test_run_no_token(monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, "")

    with pytest.raises(ValueError) as excinfo:
        _run(("--account-like", "checking%123", "--target", "410.50"))

    assert "Must set YNAB access token" in str(excinfo.value)


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
def test_run_uses_token_override(sync, db, monkeypatch):
    monkeypatch.delenv(_ENV_TOKEN, raising=False)

    ret = _run(
        (
            "--account-like",
            "Checking",
            "--target",
            "500",
            "--sqlite-export-for-ynab-db",
            db,
        ),
        token_override=TOKEN,
    )

    sync.assert_called_once_with(TOKEN, Path(db), False)
    assert ret == 0


def test_run_mode_single_requires_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(())

    assert "--mode single" in str(excinfo.value)


def test_run_mode_single_rejects_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(("--account-target-pairs", "Checking=500"))

    assert "--account-target-pairs" in str(excinfo.value)


def test_run_mode_single_rejects_interactive_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(("--account-likes", "Checking"))

    assert "--account-likes" in str(excinfo.value)


def test_run_mode_batch_requires_account_target_pairs():
    with pytest.raises(ValueError) as excinfo:
        _run(("--mode", "batch"))

    assert "--account-target-pairs" in str(excinfo.value)


def test_run_mode_batch_rejects_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(("--mode", "batch", "--account-like", "Checking", "--target", "500"))

    assert "--mode batch" in str(excinfo.value)


def test_run_mode_batch_rejects_interactive_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(("--mode", "batch", "--account-likes", "Checking"))

    assert "--account-likes" in str(excinfo.value)


def test_run_mode_interactive_batch_rejects_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(
            (
                "--mode",
                "interactive-batch",
                "--account-target-pairs",
                "Checking=500",
            )
        )

    assert "--mode interactive-batch" in str(excinfo.value)


def test_run_mode_interactive_batch_rejects_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        _run(("--mode", "interactive-batch", "--account-like", "Checking"))

    assert "--account-like" in str(excinfo.value)


def test_run_mode_interactive_batch_requires_account_likes():
    with pytest.raises(ValueError) as excinfo:
        _run(("--mode", "interactive-batch"))

    assert "--account-likes" in str(excinfo.value)


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
def test_run_mode_batch(sync, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)
    with sqlite3.connect(db) as con:
        con.execute(
            """
            UPDATE transactions
            SET cleared = 'reconciled'
            WHERE account_id = (SELECT id FROM accounts WHERE name = 'Checking')
            """
        )

    ret = _run(
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
def test_run_mode_batch_preserves_pair_order(sync, db, monkeypatch, capsys):
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

    ret = _run(
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
    ("account_like", "substr"),
    (
        pytest.param("%c%", "My Plan", id="more than 1"),
        pytest.param("foo", "nothing!", id="none"),
    ),
)
def test_run_not_one_account(sync, db, monkeypatch, account_like, substr):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    with pytest.raises(ValueError) as excinfo:
        _run(
            (
                "--account-like",
                account_like,
                "--target",
                "500",
                "--sqlite-export-for-ynab-db",
                db,
            )
        )

    assert "Must have 1 total account matches" in str(excinfo.value)
    assert substr in str(excinfo.value)


def test_parse_account_targets_wraps_non_wildcard_patterns():
    target_set = _parse_account_targets(["2045=410", "Credit%=290"])

    assert target_set.account_likes == ["%2045%", "Credit%"]
    assert target_set.targets == [Decimal("410"), Decimal("290")]


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
def test_run_mode_interactive_batch_with_account_likes(sync, db, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)
    monkeypatch.setattr("builtins.input", lambda _: "430 290")

    ret = _run(
        (
            "--mode",
            "interactive-batch",
            "--account-likes",
            "Checking",
            "Credit",
            "--sqlite-export-for-ynab-db",
            db,
        )
    )

    sync.assert_called()
    assert ret == 0


@pytest.mark.asyncio
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_run_do_reconcile(sync, db, mock_aioresponses):
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row

        cur = con.cursor()

        transactions = fetch_transactions(cur, fetch_plan_accts(cur, ["%checking%"]))[0]

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
async def test_run_do_reconcile_error_4034(sync, db, mock_aioresponses):
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row

        cur = con.cursor()

        transactions = fetch_transactions(cur, fetch_plan_accts(cur, ["%checking%"]))[0]

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
