import sqlite3
from unittest.mock import AsyncMock
from unittest.mock import patch

import aiohttp
import aiosqlite
import pytest

from manager_for_ynab.delete_payees import _find_unused_payees
from manager_for_ynab.delete_payees import _load_server_knowledge
from manager_for_ynab.delete_payees import _resolve_payees
from manager_for_ynab.delete_payees import _resolve_plan_id
from manager_for_ynab.delete_payees import delete_payees
from manager_for_ynab.delete_payees import run
from testing.fixtures import EMPLOYER_PAYEE_ID
from testing.fixtures import PLAN_ID
from testing.fixtures import TRANSFER_PAYEE_ID
from testing.fixtures import apply_ddl
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
async def test_resolve_plan_id_raises_when_no_plans(tmp_path):
    path = tmp_path / "no-plans.sqlite"
    with sqlite3.connect(path) as con:
        apply_ddl(con)

    async with aiosqlite.connect(path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _resolve_plan_id(con, None)

    assert "No plans found in this YNAB account." in str(excinfo.value)


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
async def test_resolve_payees_matches_exact_ids(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        resolved = await _resolve_payees(
            con, PLAN_ID, [EMPLOYER_PAYEE_ID, TRANSFER_PAYEE_ID]
        )

    assert resolved == [
        (EMPLOYER_PAYEE_ID, "Employer"),
        (TRANSFER_PAYEE_ID, "Transfer"),
    ]


@pytest.mark.asyncio
async def test_resolve_payees_raises_when_any_id_missing(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _resolve_payees(con, PLAN_ID, [EMPLOYER_PAYEE_ID, "nonexistent-id"])

    assert "No payee found matching id(s): nonexistent-id." in str(excinfo.value)


@pytest.mark.asyncio
async def test_find_unused_payees_excludes_transfer_payees(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        found = await _find_unused_payees(con, PLAN_ID)

    assert found == [(EMPLOYER_PAYEE_ID, "Employer")]


@patch("manager_for_ynab.delete_payees.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_dry_run_does_not_touch_session(sync_mock, db_path, capsys):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync_mock.assert_not_awaited()
    assert f"Plan: {PLAN_ID}" in out
    assert "Payees To Delete" in out
    assert EMPLOYER_PAYEE_ID in out
    assert "Employer" in out
    assert "Use --for-real to actually delete the payees." in out


@patch("manager_for_ynab.delete_payees.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_syncs_db_first_when_should_sync(
    sync_mock, db_path, capsys
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=True,
        token_override="token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync_mock.assert_awaited_once_with("token", db_path, False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out


@pytest.mark.asyncio
async def test_delete_payees_returns_one_when_resolution_fails(db_path):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=["nonexistent-id"],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    assert ret == 1


@pytest.mark.asyncio
async def test_delete_payees_reports_when_no_unused_payees_found(db_path, capsys):
    async with aiosqlite.connect(db_path) as con:
        await con.execute(
            "INSERT INTO transactions (id, plan_id, payee_id, approved, deleted) "
            "VALUES ('txn-1', ?, ?, 1, 0)",
            (PLAN_ID, EMPLOYER_PAYEE_ID),
        )
        await con.commit()

    ret = await delete_payees(
        plan_id=None,
        payee_ids=None,
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert f"No unused payees found in plan {PLAN_ID}." in out


@patch("manager_for_ynab.delete_payees.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_finds_unused_payees_when_ids_omitted(
    sync_mock, db_path, capsys
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=None,
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync_mock.assert_not_awaited()
    assert EMPLOYER_PAYEE_ID in out
    assert "Employer" in out


@patch(
    "manager_for_ynab.delete_payees.resolve_session_token",
    return_value="session-token-value",
)
@patch(
    "manager_for_ynab.delete_payees.resolve_session_cookie", return_value="cookie-value"
)
@patch("manager_for_ynab.delete_payees.delete_payee_entity", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_calls_sync_api_for_each_payee(
    delete_payee_entity_mock,
    resolve_cookie_mock,
    resolve_session_token_mock,
    db_path,
    capsys,
):
    delete_payee_entity_mock.side_effect = [
        {"error": None, "current_server_knowledge": 7020},
        {"error": None, "current_server_knowledge": 7021},
    ]

    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID, TRANSFER_PAYEE_ID],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
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
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=True,
        db=path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    out, _ = capsys.readouterr()
    assert ret == 1
    assert "Run with --sync first." in out


@patch(
    "manager_for_ynab.delete_payees.resolve_session_cookie",
    side_effect=ValueError("no cookie"),
)
@pytest.mark.asyncio
async def test_delete_payees_for_real_returns_one_when_session_auth_missing(
    resolve_cookie_mock, db_path
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    assert ret == 1


@patch(
    "manager_for_ynab.delete_payees.resolve_session_token",
    return_value="session-token-value",
)
@patch(
    "manager_for_ynab.delete_payees.resolve_session_cookie", return_value="cookie-value"
)
@patch("manager_for_ynab.delete_payees.delete_payee_entity", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_reports_client_error(
    delete_payee_entity_mock,
    resolve_cookie_mock,
    resolve_session_token_mock,
    db_path,
    capsys,
):
    delete_payee_entity_mock.side_effect = aiohttp.ClientError("boom")

    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
    )

    _, err = capsys.readouterr()
    assert ret == 1
    assert "Failed to delete payee 'Employer'" in err


@pytest.mark.token_env("")
@pytest.mark.asyncio
async def test_run_requires_token():
    with pytest.raises(ValueError) as excinfo:
        await run(("--payee-ids", "some-payee-id"))

    assert "Must set YNAB access token" in str(excinfo.value)


@patch("manager_for_ynab.delete_payees.delete_payees", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_run_delegates_parsed_args(delete_payees_mock):
    delete_payees_mock.return_value = 0

    ret = await run(
        (
            "--plan-id",
            "plan-1",
            "--payee-ids",
            EMPLOYER_PAYEE_ID,
            "--payee-ids",
            TRANSFER_PAYEE_ID,
            "--for-real",
            "--no-sync",
        ),
        token_override="override-token",
    )

    assert ret == 0
    delete_payees_mock.assert_awaited_once()
    _, kwargs = delete_payees_mock.call_args
    assert kwargs["plan_id"] == "plan-1"
    assert kwargs["payee_ids"] == [EMPLOYER_PAYEE_ID, TRANSFER_PAYEE_ID]
    assert kwargs["for_real"] is True
    assert kwargs["should_sync"] is False
    assert kwargs["token_override"] == "override-token"
