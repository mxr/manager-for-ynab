import json
import sqlite3
import sys
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import aiohttp
import aiosqlite
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from manager_for_ynab.delete_payees import _find_unused_payees
from manager_for_ynab.delete_payees import _load_server_knowledge
from manager_for_ynab.delete_payees import _resolve_payees
from manager_for_ynab.delete_payees import _resolve_plan_id
from manager_for_ynab.delete_payees import delete_payees
from manager_for_ynab.delete_payees import run
from manager_for_ynab.delete_payees._browser_session import (
    _cookie_header_to_playwright_cookies,
)
from manager_for_ynab.delete_payees._browser_session import (
    _ensure_playwright_firefox_installed,
)
from manager_for_ynab.delete_payees._browser_session import _firefox_cookie_db_paths
from manager_for_ynab.delete_payees._browser_session import _read_session_cookie_value
from manager_for_ynab.delete_payees._browser_session import (
    capture_session_token_via_browser,
)
from manager_for_ynab.delete_payees._browser_session import find_browser_cookie_header
from manager_for_ynab.delete_payees._browser_session import resolve_session_cookie
from manager_for_ynab.delete_payees._browser_session import resolve_session_token
from manager_for_ynab.delete_payees._session_token_store import load_session_token
from manager_for_ynab.delete_payees._session_token_store import save_session_token
from manager_for_ynab.delete_payees._ynab_sync_api import (
    delete_payees as delete_payees_batch_api,
)
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


@pytest.fixture
def session_token_db_path(tmp_path):
    return tmp_path / "session-token.sqlite"


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
async def test_delete_payees_dry_run_does_not_touch_session(
    sync_mock, db_path, session_token_db_path, capsys
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
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
    sync_mock, db_path, session_token_db_path, capsys
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=True,
        token_override="token",
        session_token_db=session_token_db_path,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync_mock.assert_awaited_once_with("token", db_path, False)
    assert "** Refreshing SQLite DB **" in out
    assert "** Done **" in out


@pytest.mark.asyncio
async def test_delete_payees_returns_one_when_resolution_fails(
    db_path, session_token_db_path
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=["nonexistent-id"],
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
    )

    assert ret == 1


@pytest.mark.asyncio
async def test_delete_payees_reports_when_no_unused_payees_found(
    db_path, session_token_db_path, capsys
):
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
        session_token_db=session_token_db_path,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert f"No unused payees found in plan {PLAN_ID}." in out


@patch("manager_for_ynab.delete_payees.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_finds_unused_payees_when_ids_omitted(
    sync_mock, db_path, session_token_db_path, capsys
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=None,
        for_real=False,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
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
@patch("manager_for_ynab.delete_payees.delete_payees_batch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_batches_payees_in_one_request(
    delete_payees_batch_mock,
    resolve_cookie_mock,
    resolve_session_token_mock,
    db_path,
    session_token_db_path,
    capsys,
):
    delete_payees_batch_mock.return_value = {
        "error": None,
        "current_server_knowledge": 7020,
    }

    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID, TRANSFER_PAYEE_ID],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Deleted payee 'Employer'." in out
    assert "Deleted payee 'Transfer'." in out
    delete_payees_batch_mock.assert_awaited_once()

    _, kwargs = delete_payees_batch_mock.call_args
    assert kwargs["payees"] == (
        (EMPLOYER_PAYEE_ID, "Employer"),
        (TRANSFER_PAYEE_ID, "Transfer"),
    )
    assert kwargs["starting_device_knowledge"] == 0
    assert kwargs["ending_device_knowledge"] == 2
    assert kwargs["device_knowledge_of_server"] == 7019


@patch(
    "manager_for_ynab.delete_payees.resolve_session_token",
    return_value="session-token-value",
)
@patch(
    "manager_for_ynab.delete_payees.resolve_session_cookie", return_value="cookie-value"
)
@patch("manager_for_ynab.delete_payees.delete_payees_batch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_splits_into_configured_batch_size(
    delete_payees_batch_mock,
    resolve_cookie_mock,
    resolve_session_token_mock,
    db_path,
    session_token_db_path,
    capsys,
):
    delete_payees_batch_mock.side_effect = [
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
        session_token_db=session_token_db_path,
        batch_size=1,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Deleted payee 'Employer'." in out
    assert "Deleted payee 'Transfer'." in out
    assert delete_payees_batch_mock.await_count == 2

    first_call, second_call = delete_payees_batch_mock.call_args_list
    assert first_call.kwargs["payees"] == ((EMPLOYER_PAYEE_ID, "Employer"),)
    assert first_call.kwargs["starting_device_knowledge"] == 0
    assert first_call.kwargs["ending_device_knowledge"] == 1
    assert first_call.kwargs["device_knowledge_of_server"] == 7019

    assert second_call.kwargs["payees"] == ((TRANSFER_PAYEE_ID, "Transfer"),)
    assert second_call.kwargs["starting_device_knowledge"] == 1
    assert second_call.kwargs["ending_device_knowledge"] == 2
    assert second_call.kwargs["device_knowledge_of_server"] == 7020


@pytest.mark.asyncio
async def test_delete_payees_for_real_returns_one_when_never_synced(
    tmp_path, session_token_db_path, capsys
):
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
        session_token_db=session_token_db_path,
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
    resolve_cookie_mock, db_path, session_token_db_path
):
    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
    )

    assert ret == 1


@patch(
    "manager_for_ynab.delete_payees.resolve_session_token",
    return_value="session-token-value",
)
@patch(
    "manager_for_ynab.delete_payees.resolve_session_cookie", return_value="cookie-value"
)
@patch("manager_for_ynab.delete_payees.delete_payees_batch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_reports_client_error(
    delete_payees_batch_mock,
    resolve_cookie_mock,
    resolve_session_token_mock,
    db_path,
    session_token_db_path,
    capsys,
):
    delete_payees_batch_mock.side_effect = aiohttp.ClientError("boom")

    ret = await delete_payees(
        plan_id=None,
        payee_ids=[EMPLOYER_PAYEE_ID],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
    )

    _, err = capsys.readouterr()
    assert ret == 1
    assert "Failed to delete payees 'Employer'" in err


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


def _create_cookie_db(path, cookies):
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT)")
        con.executemany(
            "INSERT INTO moz_cookies (host, name, value) VALUES (?, ?, ?)", cookies
        )


@pytest.mark.parametrize(
    ("cookies", "expected"),
    [
        pytest.param(
            [
                ("app.ynab.com", "_ynab_api_session", "abc"),
                (".app.ynab.com", "_ynab_api_session", "wrong-host"),
                ("app.ynab.com", "g_state", "def"),
                ("example.com", "_ynab_api_session", "wrong-host"),
            ],
            "abc",
            id="matches_exact_host_and_name",
        ),
        pytest.param(
            [("example.com", "_ynab_api_session", "abc")],
            None,
            id="no_match_returns_none",
        ),
    ],
)
@pytest.mark.asyncio
async def test_read_session_cookie_value(tmp_path, cookies, expected):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(db_path, cookies)

    assert await _read_session_cookie_value(db_path) == expected


@patch("manager_for_ynab.delete_payees._browser_session.Path.home")
def test_firefox_cookie_db_paths_finds_macos_and_linux_profiles(home_mock, tmp_path):
    home_mock.return_value = tmp_path
    macos_profile = (
        tmp_path / "Library" / "Application Support" / "Firefox" / "Profiles" / "abc"
    )
    macos_profile.mkdir(parents=True)
    (macos_profile / "cookies.sqlite").touch()
    linux_profile = tmp_path / ".mozilla" / "firefox" / "xyz"
    linux_profile.mkdir(parents=True)
    (linux_profile / "cookies.sqlite").touch()

    paths = _firefox_cookie_db_paths()

    assert paths == sorted(
        [macos_profile / "cookies.sqlite", linux_profile / "cookies.sqlite"]
    )


@patch("manager_for_ynab.delete_payees._browser_session.Path.home")
def test_firefox_cookie_db_paths_returns_empty_without_profile_dirs(
    home_mock, tmp_path
):
    home_mock.return_value = tmp_path
    assert _firefox_cookie_db_paths() == []


@patch(
    "manager_for_ynab.delete_payees._browser_session._firefox_cookie_db_paths",
    return_value=[],
)
@pytest.mark.asyncio
async def test_find_browser_cookie_header_returns_none_without_profiles(
    db_paths_mock, tmp_path
):
    assert await find_browser_cookie_header() is None


@patch("manager_for_ynab.delete_payees._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_returns_cookie_header(
    db_paths_mock, tmp_path
):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(db_path, [("app.ynab.com", "_ynab_api_session", "1")])
    db_paths_mock.return_value = [db_path]

    assert await find_browser_cookie_header() == "_ynab_api_session=1"


@patch("manager_for_ynab.delete_payees._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_skips_unreadable_db(db_paths_mock, tmp_path):
    bad_db = tmp_path / "bad.sqlite"
    bad_db.write_text("not a sqlite file")
    good_db = tmp_path / "good.sqlite"
    _create_cookie_db(good_db, [("app.ynab.com", "_ynab_api_session", "1")])
    db_paths_mock.return_value = [bad_db, good_db]

    assert await find_browser_cookie_header() == "_ynab_api_session=1"


@patch("manager_for_ynab.delete_payees._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_skips_db_with_no_matching_cookies(
    db_paths_mock, tmp_path
):
    empty_db = tmp_path / "empty.sqlite"
    _create_cookie_db(empty_db, [("example.com", "_ynab_api_session", "1")])
    good_db = tmp_path / "good.sqlite"
    _create_cookie_db(good_db, [("app.ynab.com", "_ynab_api_session", "2")])
    db_paths_mock.return_value = [empty_db, good_db]

    assert await find_browser_cookie_header() == "_ynab_api_session=2"


@patch(
    "manager_for_ynab.delete_payees._browser_session.find_browser_cookie_header",
    return_value="from-browser",
)
@pytest.mark.asyncio
async def test_resolve_session_cookie_reads_from_browser(find_cookie_header):
    assert await resolve_session_cookie() == "from-browser"


@patch(
    "manager_for_ynab.delete_payees._browser_session.find_browser_cookie_header",
    return_value=None,
)
@pytest.mark.asyncio
async def test_resolve_session_cookie_raises_when_nothing_found(find_cookie_header):
    with pytest.raises(ValueError) as excinfo:
        await resolve_session_cookie()

    assert "Firefox" in str(excinfo.value)


@pytest.mark.asyncio
async def test_resolve_session_token_uses_stored_token(
    session_token_db_path,
):
    await save_session_token(session_token_db_path, "from-store")

    assert (
        await resolve_session_token(db=session_token_db_path, cookie="cookie-value")
        == "from-store"
    )


@patch(
    "manager_for_ynab.delete_payees._browser_session.capture_session_token_via_browser",
    new_callable=AsyncMock,
    return_value="from-browser",
)
@pytest.mark.asyncio
async def test_resolve_session_token_captures_and_persists_via_browser(
    capture_mock, session_token_db_path
):
    result = await resolve_session_token(
        db=session_token_db_path, cookie="cookie-value"
    )

    assert result == "from-browser"
    assert await load_session_token(session_token_db_path) == "from-browser"
    capture_mock.assert_awaited_once_with(cookie="cookie-value")


@patch(
    "manager_for_ynab.delete_payees._browser_session.capture_session_token_via_browser",
    new_callable=AsyncMock,
    side_effect=TimeoutError,
)
@pytest.mark.asyncio
async def test_resolve_session_token_raises_when_browser_capture_times_out(
    capture_mock, session_token_db_path
):
    with pytest.raises(ValueError) as excinfo:
        await resolve_session_token(db=session_token_db_path, cookie="cookie-value")

    assert "Timed out" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ensure_playwright_firefox_installed_skips_when_already_installed(
    tmp_path,
):
    executable = tmp_path / "firefox"
    executable.touch()
    firefox = MagicMock(executable_path=str(executable))

    with patch("asyncio.create_subprocess_exec") as create_subprocess_exec_mock:
        await _ensure_playwright_firefox_installed(firefox)

    create_subprocess_exec_mock.assert_not_called()


@pytest.mark.parametrize(
    ("exit_code", "expected_error"),
    [
        pytest.param(0, None, id="succeeds"),
        pytest.param(1, "exit code 1", id="raises_on_nonzero_exit"),
    ],
)
@pytest.mark.asyncio
async def test_ensure_playwright_firefox_installed_when_missing(
    tmp_path, exit_code, expected_error
):
    executable = tmp_path / "firefox"
    firefox = MagicMock(executable_path=str(executable))
    proc_mock = AsyncMock()
    proc_mock.wait.return_value = exit_code

    with patch(
        "asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc_mock,
    ) as create_subprocess_exec_mock:
        if expected_error is None:
            await _ensure_playwright_firefox_installed(firefox)
        else:
            with pytest.raises(RuntimeError) as excinfo:
                await _ensure_playwright_firefox_installed(firefox)
            assert expected_error in str(excinfo.value)

    create_subprocess_exec_mock.assert_awaited_once_with(
        sys.executable, "-m", "playwright", "install", "firefox"
    )


def test_cookie_header_to_playwright_cookies():
    cookies = _cookie_header_to_playwright_cookies("a=1; b=2")

    assert cookies == [
        {"name": "a", "value": "1", "domain": ".ynab.com", "path": "/"},
        {"name": "b", "value": "2", "domain": ".ynab.com", "path": "/"},
    ]


class _AsyncContextManager:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info):
        return False


@patch(
    "manager_for_ynab.delete_payees._browser_session._ensure_playwright_firefox_installed",
    new_callable=AsyncMock,
)
@patch("playwright.async_api.async_playwright")
@pytest.mark.asyncio
async def test_capture_session_token_via_browser_returns_captured_token(
    async_playwright_mock, ensure_firefox_mock
):
    page_mock = MagicMock()
    captured_handlers: dict[str, Callable[[MagicMock], None]] = {}
    page_mock.on = MagicMock(
        side_effect=lambda event, handler: captured_handlers.__setitem__(event, handler)
    )

    async def _goto(url):
        no_token_request = MagicMock()
        no_token_request.headers.get.return_value = None
        captured_handlers["request"](no_token_request)

        token_request = MagicMock()
        token_request.headers.get.return_value = "captured-token"
        captured_handlers["request"](token_request)

        captured_handlers["request"](token_request)

    page_mock.goto = AsyncMock(side_effect=_goto)

    context_mock = MagicMock()
    context_mock.add_cookies = AsyncMock()
    context_mock.new_page = AsyncMock(return_value=page_mock)

    browser_mock = MagicMock()
    browser_mock.new_context = AsyncMock(return_value=context_mock)

    playwright_mock = MagicMock()
    playwright_mock.firefox.launch = AsyncMock(
        return_value=_AsyncContextManager(browser_mock)
    )

    async_playwright_mock.return_value = _AsyncContextManager(playwright_mock)

    result = await capture_session_token_via_browser(cookie="a=1; b=2")

    assert result == "captured-token"
    context_mock.add_cookies.assert_awaited_once_with(
        [
            {"name": "a", "value": "1", "domain": ".ynab.com", "path": "/"},
            {"name": "b", "value": "2", "domain": ".ynab.com", "path": "/"},
        ]
    )
    page_mock.goto.assert_awaited_once_with("https://app.ynab.com/")


@patch(
    "manager_for_ynab.delete_payees._browser_session._ensure_playwright_firefox_installed",
    new_callable=AsyncMock,
)
@patch("playwright.async_api.async_playwright")
@pytest.mark.asyncio
async def test_capture_session_token_via_browser_raises_on_timeout(
    async_playwright_mock, ensure_firefox_mock
):
    page_mock = MagicMock()
    page_mock.on = MagicMock()
    page_mock.goto = AsyncMock()

    context_mock = MagicMock()
    context_mock.add_cookies = AsyncMock()
    context_mock.new_page = AsyncMock(return_value=page_mock)

    browser_mock = MagicMock()
    browser_mock.new_context = AsyncMock(return_value=context_mock)

    playwright_mock = MagicMock()
    playwright_mock.firefox.launch = AsyncMock(
        return_value=_AsyncContextManager(browser_mock)
    )

    async_playwright_mock.return_value = _AsyncContextManager(playwright_mock)

    with pytest.raises(TimeoutError):
        await capture_session_token_via_browser(cookie="a=1", timeout=0)


class _FakeResponse:
    def __init__(self, payload=None, *, status=200, text=""):
        self._payload = payload
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


@pytest.mark.asyncio
async def test_delete_payees_batch_api_sends_tombstone_delta():
    fake_session = MagicMock()
    fake_session.post = MagicMock(
        return_value=_FakeResponse({"error": None, "current_server_knowledge": 7020})
    )

    result = await delete_payees_batch_api(
        fake_session,
        cookie="cookie-value",
        session_token="token-value",
        budget_version_id="plan-1",
        payees=[("payee-1", "Amazon Duplicate"), ("payee-2", "Employer")],
        starting_device_knowledge=5,
        ending_device_knowledge=7,
        device_knowledge_of_server=7019,
    )

    assert result == {"error": None, "current_server_knowledge": 7020}
    fake_session.post.assert_called_once()

    _, kwargs = fake_session.post.call_args
    request_data = json.loads(kwargs["data"]["request_data"])
    assert request_data["budget_version_id"] == "plan-1"
    assert request_data["starting_device_knowledge"] == 5
    assert request_data["ending_device_knowledge"] == 7
    assert request_data["device_knowledge_of_server"] == 7019
    assert kwargs["headers"]["Cookie"] == "cookie-value"
    assert kwargs["headers"]["X-Session-Token"] == "token-value"
    assert kwargs["headers"]["X-YNAB-Device-Id"]

    payee_entities = request_data["changed_entities"]["be_payees"]
    assert payee_entities[0]["id"] == "payee-1"
    assert payee_entities[0]["is_tombstone"] is True
    assert payee_entities[0]["name"] == "Amazon Duplicate"
    assert payee_entities[1]["id"] == "payee-2"
    assert payee_entities[1]["name"] == "Employer"


@pytest.mark.parametrize(
    ("fake_response", "expected_substrings"),
    [
        pytest.param(
            _FakeResponse({"error": "not authorized"}),
            ["not authorized"],
            id="error_in_response_body",
        ),
        pytest.param(
            _FakeResponse(status=400, text="Bad Request details"),
            ["400", "Bad Request details"],
            id="http_error_status",
        ),
    ],
)
@pytest.mark.asyncio
async def test_delete_payees_batch_api_raises_on_error(
    fake_response, expected_substrings
):
    fake_session = MagicMock()
    fake_session.post = MagicMock(return_value=fake_response)

    with pytest.raises(RuntimeError) as excinfo:
        await delete_payees_batch_api(
            fake_session,
            cookie="cookie-value",
            session_token="token-value",
            budget_version_id="plan-1",
            payees=[("payee-1", "Amazon Duplicate")],
            starting_device_knowledge=0,
            ending_device_knowledge=1,
            device_knowledge_of_server=0,
        )

    for substring in expected_substrings:
        assert substring in str(excinfo.value)
