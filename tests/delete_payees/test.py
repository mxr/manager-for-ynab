import sqlite3
from unittest.mock import AsyncMock
from unittest.mock import patch

import aiohttp
import aiosqlite
import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.delete_payees import _load_server_knowledge
from manager_for_ynab.delete_payees import _resolve_payees
from manager_for_ynab.delete_payees import _resolve_plan_id
from manager_for_ynab.delete_payees import delete_payees
from manager_for_ynab.delete_payees import run
from testing.fixtures import EMPLOYER_PAYEE_ID
from testing.fixtures import PLAN_ID
from testing.fixtures import TRANSFER_PAYEE_ID
from testing.fixtures import execute_seed


def _create_db(path):
    with sqlite3.connect(path) as con:
        execute_seed(con)
        con.execute(
            "UPDATE plans SET last_knowledge_of_server = 7019 WHERE id = ?", (PLAN_ID,)
        )


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "delete-payees.sqlite"
    _create_db(path)
    return path


@pytest.mark.asyncio
async def test_resolve_plan_id_uses_only_plan(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        assert await _resolve_plan_id(con, None) == PLAN_ID


@pytest.mark.asyncio
async def test_resolve_plan_id_uses_explicit_id(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        assert await _resolve_plan_id(con, PLAN_ID) == PLAN_ID


@pytest.mark.asyncio
async def test_resolve_plan_id_raises_for_unknown_id(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _resolve_plan_id(con, "unknown-plan")

    assert "No plan found with id 'unknown-plan'." in str(excinfo.value)


@pytest.mark.asyncio
async def test_resolve_plan_id_raises_when_ambiguous(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO plans (id, name) VALUES ('other-plan', 'Other Plan')")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _resolve_plan_id(con, None)

    assert "Found 2 plans" in str(excinfo.value)
    assert "Specify --plan-id." in str(excinfo.value)


@pytest.mark.asyncio
async def test_load_server_knowledge_reads_last_knowledge_of_server(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        assert await _load_server_knowledge(con, PLAN_ID) == 7019


@pytest.mark.asyncio
async def test_load_server_knowledge_raises_when_never_synced(tmp_path):
    path = tmp_path / "never-synced.sqlite"
    with sqlite3.connect(path) as con:
        execute_seed(con)

    async with aiosqlite.connect(path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _load_server_knowledge(con, PLAN_ID)

    assert "Run with --sync first." in str(excinfo.value)


@pytest.mark.asyncio
async def test_resolve_payees_matches_exact_case_insensitive_names(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        resolved = await _resolve_payees(con, PLAN_ID, ["employer", "TRANSFER"])

    assert resolved == [
        (EMPLOYER_PAYEE_ID, "Employer"),
        (TRANSFER_PAYEE_ID, "Transfer"),
    ]


@pytest.mark.asyncio
async def test_resolve_payees_raises_when_any_name_missing(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _resolve_payees(con, PLAN_ID, ["Employer", "Nonexistent"])

    assert "No payee found matching name(s): Nonexistent." in str(excinfo.value)


@patch("manager_for_ynab.delete_payees.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_dry_run_does_not_touch_session(sync_mock, db_path, capsys):
    ret = await delete_payees(
        plan_id=None,
        payee_names=["Employer"],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync_mock.assert_not_awaited()
    assert "Targeting payees 'Employer' in plan" in out
    assert "Use --for-real to actually delete the payees." in out


@pytest.mark.asyncio
async def test_delete_payees_returns_one_when_resolution_fails(db_path):
    ret = await delete_payees(
        plan_id=None,
        payee_names=["nonexistent"],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    assert ret == 1


@patch("manager_for_ynab.delete_payees.delete_payee_entity", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_calls_sync_api_for_each_payee(
    delete_payee_entity_mock, db_path, capsys
):
    delete_payee_entity_mock.side_effect = [
        {"error": None, "current_server_knowledge": 7020},
        {"error": None, "current_server_knowledge": 7021},
    ]

    ret = await delete_payees(
        plan_id=None,
        payee_names=["Employer", "Transfer"],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        cookie_override="cookie-value",
        session_token_override="session-token-value",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Deleted payee 'Employer'." in out
    assert "Deleted payee 'Transfer'." in out
    assert delete_payee_entity_mock.await_count == 2

    first_call, second_call = delete_payee_entity_mock.call_args_list
    assert first_call.kwargs["payee_id"] == EMPLOYER_PAYEE_ID
    assert first_call.kwargs["starting_device_knowledge"] == 0
    assert first_call.kwargs["ending_device_knowledge"] == 1
    assert first_call.kwargs["device_knowledge_of_server"] == 7019

    assert second_call.kwargs["payee_id"] == TRANSFER_PAYEE_ID
    assert second_call.kwargs["starting_device_knowledge"] == 1
    assert second_call.kwargs["ending_device_knowledge"] == 2
    assert second_call.kwargs["device_knowledge_of_server"] == 7020


@pytest.mark.asyncio
async def test_delete_payees_for_real_returns_one_when_never_synced(tmp_path, capsys):
    path = tmp_path / "never-synced.sqlite"
    with sqlite3.connect(path) as con:
        execute_seed(con)

    ret = await delete_payees(
        plan_id=None,
        payee_names=["Employer"],
        for_real=True,
        db=path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        cookie_override="cookie-value",
        session_token_override="session-token-value",
    )

    out, _ = capsys.readouterr()
    assert ret == 1
    assert "Run with --sync first." in out


@pytest.mark.asyncio
async def test_delete_payees_for_real_returns_one_when_session_auth_missing(db_path):
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "manager_for_ynab.delete_payees.resolve_session_cookie",
            side_effect=ValueError("no cookie"),
        ),
    ):
        ret = await delete_payees(
            plan_id=None,
            payee_names=["Employer"],
            for_real=True,
            db=db_path,
            full_refresh=False,
            should_sync=False,
            token_override="token",
        )

    assert ret == 1


@patch("manager_for_ynab.delete_payees.delete_payee_entity", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_reports_client_error(
    delete_payee_entity_mock, db_path, capsys
):
    delete_payee_entity_mock.side_effect = aiohttp.ClientError("boom")

    ret = await delete_payees(
        plan_id=None,
        payee_names=["Employer"],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        cookie_override="cookie-value",
        session_token_override="session-token-value",
    )

    _, err = capsys.readouterr()
    assert ret == 1
    assert "Failed to delete payee 'Employer'" in err


@patch.dict("os.environ", {_ENV_TOKEN: ""})
@pytest.mark.asyncio
async def test_run_requires_token():
    with pytest.raises(ValueError) as excinfo:
        await run(("--payee-name", "Employer"))

    assert "Must set YNAB access token" in str(excinfo.value)


@patch("manager_for_ynab.delete_payees.delete_payees", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_run_delegates_parsed_args(delete_payees_mock):
    delete_payees_mock.return_value = 0

    ret = await run(
        (
            "--plan-id",
            "plan-1",
            "--payee-name",
            "Employer",
            "--payee-name",
            "Transfer",
            "--for-real",
            "--no-sync",
        ),
        token_override="override-token",
    )

    assert ret == 0
    delete_payees_mock.assert_awaited_once()
    _, kwargs = delete_payees_mock.call_args
    assert kwargs["plan_id"] == "plan-1"
    assert kwargs["payee_names"] == ["Employer", "Transfer"]
    assert kwargs["for_real"] is True
    assert kwargs["should_sync"] is False
    assert kwargs["token_override"] == "override-token"
