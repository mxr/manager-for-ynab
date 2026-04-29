import json
import re
import sqlite3
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch

import aiohttp
import aiosqlite
import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.reconciler import _parse_account_targets
from manager_for_ynab.reconciler import do_reconcile
from manager_for_ynab.reconciler import fetch_plan_accts
from manager_for_ynab.reconciler import fetch_transactions
from manager_for_ynab.reconciler import run
from manager_for_ynab.reconciler import YnabClient
from testing.fixtures import CHECKING_ACCOUNT_ID
from testing.fixtures import CREDIT_CARD_ACCOUNT_ID
from testing.fixtures import db
from testing.fixtures import mock_aioresponses
from testing.fixtures import PLAN_ID
from testing.fixtures import TOKEN
from testing.fixtures import TOKEN_OVERRIDE


class FakePromptSession:
    def __init__(self, response: str) -> None:
        self.prompt_async = AsyncMock(return_value=response)


def fake_prompt_session_430() -> FakePromptSession:
    return FakePromptSession("430")


def fake_prompt_session_430_290() -> FakePromptSession:
    return FakePromptSession("430 290")


@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
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
@pytest.mark.asyncio
async def test_run(sync, db, capsys, target, expected, substr):
    ret = await run(
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


@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.asyncio
async def test_run_nothing_to_do(sync, db):
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE transactions SET cleared = 'uncleared' where cleared = 'cleared'"
        )

    ret = await run(
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


@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
@patch("manager_for_ynab.reconciler.sync")
@patch.object(YnabClient, "reconcile")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.asyncio
async def test_run_reconciles_with_for_real(reconcile, sync, db):
    ret = await run(
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


@patch.dict("os.environ", {_ENV_TOKEN: ""})
@pytest.mark.asyncio
async def test_run_no_token():
    with pytest.raises(ValueError) as excinfo:
        await run(("--account-like", "checking%123", "--target", "410.50"))

    assert "Must set YNAB access token" in str(excinfo.value)


@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.asyncio
async def test_run_uses_token_override(sync, db):
    ret = await run(
        (
            "--account-like",
            "Checking",
            "--target",
            "500",
            "--sqlite-export-for-ynab-db",
            db,
        ),
        token_override=TOKEN_OVERRIDE,
    )

    sync.assert_called_once_with(TOKEN_OVERRIDE, Path(db), False)
    assert ret == 0


@pytest.mark.asyncio
async def test_run_mode_single_requires_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(())

    assert "--mode single" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_single_rejects_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(("--account-target-pairs", "Checking=500"))

    assert "--account-target-pairs" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_single_rejects_interactive_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(("--account-likes", "Checking"))

    assert "--account-likes" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_batch_requires_account_target_pairs():
    with pytest.raises(ValueError) as excinfo:
        await run(("--mode", "batch"))

    assert "--account-target-pairs" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_batch_rejects_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(("--mode", "batch", "--account-like", "Checking", "--target", "500"))

    assert "--mode batch" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_batch_rejects_interactive_batch_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(("--mode", "batch", "--account-likes", "Checking"))

    assert "--account-likes" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_interactive_batch_rejects_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(
            (
                "--mode",
                "interactive-batch",
                "--account-target-pairs",
                "Checking=500",
            )
        )

    assert "--mode interactive-batch" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_interactive_batch_rejects_single_targeting_params():
    with pytest.raises(ValueError) as excinfo:
        await run(("--mode", "interactive-batch", "--account-like", "Checking"))

    assert "--account-like" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_mode_interactive_batch_requires_account_likes():
    with pytest.raises(ValueError) as excinfo:
        await run(("--mode", "interactive-batch"))

    assert "--account-likes" in str(excinfo.value)


@patch(
    "manager_for_ynab.reconciler.PromptSession",
    new=fake_prompt_session_430,
)
@patch("manager_for_ynab.reconciler.patch_stdout", return_value=nullcontext())
@pytest.mark.asyncio
async def test_run_mode_interactive_batch_requires_matching_target_count(_):
    with pytest.raises(ValueError) as excinfo:
        await run(
            (
                "--mode",
                "interactive-batch",
                "--account-likes",
                "Checking",
                "Credit",
            )
        )

    assert "requires 2 target balances" in str(excinfo.value)


@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.asyncio
async def test_run_mode_batch(sync, db):
    with sqlite3.connect(db) as con:
        con.execute(
            """
            UPDATE transactions
            SET cleared = 'reconciled'
            WHERE account_id = ?
            """,
            (CHECKING_ACCOUNT_ID,),
        )

    ret = await run(
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


@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.asyncio
async def test_run_mode_batch_preserves_pair_order(sync, db, capsys):
    with sqlite3.connect(db) as con:
        con.execute(
            """
            UPDATE transactions
            SET cleared = 'uncleared'
            WHERE account_id IN (?, ?)
            AND cleared != 'reconciled'
            """,
            (CHECKING_ACCOUNT_ID, CREDIT_CARD_ACCOUNT_ID),
        )

    ret = await run(
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


@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.parametrize(
    ("account_like", "substr"),
    (
        pytest.param("%c%", "My Plan", id="more than 1"),
        pytest.param("foo", "nothing!", id="none"),
    ),
)
@pytest.mark.asyncio
async def test_run_not_one_account(sync, db, account_like, substr):
    with pytest.raises(ValueError) as excinfo:
        await run(
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


@pytest.mark.asyncio
@pytest.mark.usefixtures(db.__name__)
async def test_fetch_transactions_filters_unapproved(db):
    with sqlite3.connect(db) as con:
        con.execute(
            """
            UPDATE transactions
            SET approved = 0
            WHERE id = 'c479c335-b54f-48b9-8b74-49a907f1b3f2'
            """
        )

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        transactions = (
            await fetch_transactions(con, await fetch_plan_accts(con, ["%Checking%"]))
        )[0]

    assert {txn.id for txn in transactions} == {
        "9a97f337-28db-4c2d-990f-d9ec0e9bc765",
        "96817e5f-d272-4012-9790-38f8a8e2be90",
        "eeef0922-b226-4f8a-bf00-66d4d98e348c",
    }


@patch("manager_for_ynab.reconciler.sync")
@patch(
    "manager_for_ynab.reconciler.PromptSession",
    new=fake_prompt_session_430_290,
)
@patch("manager_for_ynab.reconciler.patch_stdout", return_value=nullcontext())
@pytest.mark.usefixtures(db.__name__)
@patch.dict("os.environ", {_ENV_TOKEN: TOKEN})
@pytest.mark.asyncio
async def test_run_mode_interactive_batch_with_account_likes(_, sync, db):
    ret = await run(
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
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        transactions = (
            await fetch_transactions(con, await fetch_plan_accts(con, ["%checking%"]))
        )[0]

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

    async with aiohttp.ClientSession() as session:
        await do_reconcile(session, TOKEN, PLAN_ID, transactions, "Reconciling")


@pytest.mark.asyncio
@patch("manager_for_ynab.reconciler.sync")
@pytest.mark.usefixtures(db.__name__)
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_run_do_reconcile_error_4034(sync, db, mock_aioresponses):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        transactions = (
            await fetch_transactions(con, await fetch_plan_accts(con, ["%checking%"]))
        )[0]

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

    async with aiohttp.ClientSession() as session:
        await do_reconcile(session, TOKEN, PLAN_ID, transactions, "Reconciling")
