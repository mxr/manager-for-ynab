from __future__ import annotations

import json
import sqlite3
import sys
from typing import TYPE_CHECKING
from unittest.mock import ANY
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import call
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
    _ensure_playwright_firefox_installed,
)
from manager_for_ynab.delete_payees._browser_session import (
    capture_web_session_via_browser,
)
from manager_for_ynab.delete_payees._browser_session import resolve_web_session
from manager_for_ynab.delete_payees._session_token_store import WebSession
from manager_for_ynab.delete_payees._session_token_store import load_web_session
from manager_for_ynab.delete_payees._session_token_store import save_web_session
from manager_for_ynab.delete_payees._ynab_sync_api import (
    delete_payees as delete_payees_batch_api,
)
from testing.fixtures import EMPLOYER_PAYEE_ID
from testing.fixtures import PLAN_ID
from testing.fixtures import TRANSFER_PAYEE_ID
from testing.fixtures import apply_ddl
from testing.fixtures import execute_seed
from testing.fixtures import seed_paths


@pytest.fixture
def db_path(request, tmp_path):
    path = tmp_path / "delete-payees.sqlite"
    with sqlite3.connect(path) as con:
        execute_seed(con, *seed_paths(request))
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


@pytest.mark.seed("seed-other-plan.sql")
@pytest.mark.asyncio
async def test_resolve_plan_id_raises_when_ambiguous(db_path):
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


@pytest.mark.seed("seed-other-plan.sql")
@pytest.mark.asyncio
async def test_load_server_knowledge_raises_when_never_synced(db_path):
    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as excinfo:
            await _load_server_knowledge(con, "other-plan")

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


@pytest.mark.seed("seed-other-plan.sql")
@pytest.mark.asyncio
async def test_delete_payees_reports_when_no_unused_payees_found(
    db_path, session_token_db_path, capsys
):
    ret = await delete_payees(
        plan_id="other-plan",
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
    assert "No unused payees found in plan other-plan." in out


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
    "manager_for_ynab.delete_payees.resolve_web_session",
    return_value=WebSession(cookie="cookie-value", token="session-token-value"),
)
@patch("manager_for_ynab.delete_payees.delete_payees_batch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_batches_payees_in_one_request(
    delete_payees_batch_mock,
    resolve_web_session_mock,
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
    delete_payees_batch_mock.assert_awaited_once_with(
        ANY,
        cookie=ANY,
        session_token=ANY,
        budget_version_id=ANY,
        payees=((EMPLOYER_PAYEE_ID, "Employer"), (TRANSFER_PAYEE_ID, "Transfer")),
        starting_device_knowledge=0,
        ending_device_knowledge=2,
        device_knowledge_of_server=7019,
    )


@patch(
    "manager_for_ynab.delete_payees.resolve_web_session",
    return_value=WebSession(cookie="cookie-value", token="session-token-value"),
)
@patch("manager_for_ynab.delete_payees.delete_payees_batch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_splits_into_configured_batch_size(
    delete_payees_batch_mock,
    resolve_web_session_mock,
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
    assert delete_payees_batch_mock.await_args_list == [
        call(
            ANY,
            cookie=ANY,
            session_token=ANY,
            budget_version_id=ANY,
            payees=((EMPLOYER_PAYEE_ID, "Employer"),),
            starting_device_knowledge=0,
            ending_device_knowledge=1,
            device_knowledge_of_server=7019,
        ),
        call(
            ANY,
            cookie=ANY,
            session_token=ANY,
            budget_version_id=ANY,
            payees=((TRANSFER_PAYEE_ID, "Transfer"),),
            starting_device_knowledge=1,
            ending_device_knowledge=2,
            device_knowledge_of_server=7020,
        ),
    ]


@pytest.mark.seed("seed-other-plan.sql")
@pytest.mark.asyncio
async def test_delete_payees_for_real_returns_one_when_never_synced(
    db_path, session_token_db_path, capsys
):
    ret = await delete_payees(
        plan_id="other-plan",
        payee_ids=["other-plan-payee"],
        for_real=True,
        db=db_path,
        full_refresh=False,
        should_sync=False,
        token_override="token",
        session_token_db=session_token_db_path,
    )

    out, _ = capsys.readouterr()
    assert ret == 1
    assert "Run with --sync first." in out


@patch("manager_for_ynab.delete_payees.find_spec", return_value=None)
@pytest.mark.asyncio
async def test_delete_payees_for_real_raises_when_playwright_missing(
    find_spec_mock, db_path, session_token_db_path
):
    with pytest.raises(ImportError, match="manager-for-ynab\\[delete-payees\\]"):
        await delete_payees(
            plan_id=None,
            payee_ids=[EMPLOYER_PAYEE_ID],
            for_real=True,
            db=db_path,
            full_refresh=False,
            should_sync=False,
            token_override="token",
            session_token_db=session_token_db_path,
        )


@patch(
    "manager_for_ynab.delete_payees.resolve_web_session",
    side_effect=ValueError("no session"),
)
@pytest.mark.asyncio
async def test_delete_payees_for_real_returns_one_when_session_auth_missing(
    resolve_web_session_mock, db_path, session_token_db_path
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
    "manager_for_ynab.delete_payees.resolve_web_session",
    return_value=WebSession(cookie="cookie-value", token="session-token-value"),
)
@patch("manager_for_ynab.delete_payees.delete_payees_batch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_payees_for_real_reports_client_error(
    delete_payees_batch_mock,
    resolve_web_session_mock,
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
    delete_payees_mock.assert_awaited_once_with(
        plan_id="plan-1",
        payee_ids=[EMPLOYER_PAYEE_ID, TRANSFER_PAYEE_ID],
        for_real=True,
        db=ANY,
        full_refresh=ANY,
        should_sync=False,
        token_override="override-token",
        session_token_db=ANY,
        batch_size=ANY,
    )


@pytest.mark.asyncio
async def test_load_web_session_returns_none_without_db(session_token_db_path):
    assert await load_web_session(session_token_db_path) is None


@pytest.mark.asyncio
async def test_load_web_session_ignores_legacy_token_only_db(session_token_db_path):
    with sqlite3.connect(session_token_db_path) as con:
        con.execute(
            "CREATE TABLE session_token (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        con.execute("INSERT INTO session_token (id, value) VALUES (1, 'old-token')")

    assert await load_web_session(session_token_db_path) is None


@pytest.mark.asyncio
async def test_save_web_session_overwrites_previous(session_token_db_path):
    await save_web_session(session_token_db_path, WebSession(cookie="c1", token="t1"))
    await save_web_session(session_token_db_path, WebSession(cookie="c2", token="t2"))

    assert await load_web_session(session_token_db_path) == WebSession(
        cookie="c2", token="t2"
    )


@patch(
    "manager_for_ynab.delete_payees._browser_session.capture_web_session_via_browser",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_resolve_web_session_uses_stored_session(
    capture_mock, session_token_db_path
):
    stored = WebSession(cookie="from-store", token="from-store")
    await save_web_session(session_token_db_path, stored)

    assert await resolve_web_session(db=session_token_db_path) == stored
    capture_mock.assert_not_awaited()


@patch(
    "manager_for_ynab.delete_payees._browser_session.capture_web_session_via_browser",
    new_callable=AsyncMock,
    return_value=WebSession(cookie="from-browser", token="from-browser"),
)
@pytest.mark.asyncio
async def test_resolve_web_session_captures_and_persists_via_browser(
    capture_mock, session_token_db_path
):
    result = await resolve_web_session(db=session_token_db_path)

    assert result == WebSession(cookie="from-browser", token="from-browser")
    assert await load_web_session(session_token_db_path) == result
    capture_mock.assert_awaited_once_with(
        profile_dir=session_token_db_path.parent / "browser-profile"
    )


@patch(
    "manager_for_ynab.delete_payees._browser_session.capture_web_session_via_browser",
    new_callable=AsyncMock,
    side_effect=TimeoutError,
)
@pytest.mark.asyncio
async def test_resolve_web_session_raises_when_browser_capture_times_out(
    capture_mock, session_token_db_path
):
    with pytest.raises(ValueError) as excinfo:
        await resolve_web_session(db=session_token_db_path)

    assert "Timed out" in str(excinfo.value)
    assert await load_web_session(session_token_db_path) is None


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


class _AsyncContextManager:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info):
        return False


@pytest.fixture
def browser_mocks():
    page_mock = MagicMock()
    page_mock.on = MagicMock()
    page_mock.goto = AsyncMock()

    context_mock = MagicMock()
    context_mock.new_page = AsyncMock(return_value=page_mock)
    context_mock.cookies = AsyncMock(
        return_value=[
            {"name": "other", "value": "x"},
            {"name": "_ynab_api_session", "value": "abc"},
        ]
    )

    playwright_mock = MagicMock()
    playwright_mock.firefox.launch_persistent_context = AsyncMock(
        return_value=_AsyncContextManager(context_mock)
    )

    with (
        patch(
            "manager_for_ynab.delete_payees._browser_session._ensure_playwright_firefox_installed",
            new_callable=AsyncMock,
        ),
        patch(
            "playwright.async_api.async_playwright",
            return_value=_AsyncContextManager(playwright_mock),
        ),
    ):
        yield playwright_mock, context_mock, page_mock


def _emit_requests_on_goto(page_mock, header_values):
    captured_handlers: dict[str, Callable[[MagicMock], None]] = {}
    page_mock.on.side_effect = lambda event, handler: captured_handlers.__setitem__(
        event, handler
    )

    async def _goto(url):
        for value in header_values:
            request = MagicMock()
            request.headers.get.return_value = value
            captured_handlers["request"](request)

    page_mock.goto.side_effect = _goto


@pytest.mark.asyncio
async def test_capture_web_session_via_browser_returns_cookie_and_token(
    browser_mocks, tmp_path
):
    playwright_mock, context_mock, page_mock = browser_mocks
    _emit_requests_on_goto(page_mock, [None, "captured-token", "later-token"])

    result = await capture_web_session_via_browser(profile_dir=tmp_path)

    assert result == WebSession(cookie="_ynab_api_session=abc", token="captured-token")
    playwright_mock.firefox.launch_persistent_context.assert_awaited_once_with(
        tmp_path, headless=False
    )
    page_mock.goto.assert_awaited_once_with("https://app.ynab.com/")
    context_mock.cookies.assert_awaited_once_with("https://app.ynab.com/")


@pytest.mark.asyncio
async def test_capture_web_session_via_browser_raises_without_session_cookie(
    browser_mocks, tmp_path
):
    _, context_mock, page_mock = browser_mocks
    _emit_requests_on_goto(page_mock, ["captured-token"])
    context_mock.cookies.return_value = [{"name": "other", "value": "x"}]

    with pytest.raises(ValueError, match="_ynab_api_session"):
        await capture_web_session_via_browser(profile_dir=tmp_path)


@pytest.mark.asyncio
async def test_capture_web_session_via_browser_raises_on_timeout(
    browser_mocks, tmp_path
):
    with pytest.raises(TimeoutError):
        await capture_web_session_via_browser(profile_dir=tmp_path, timeout=0)


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
    fake_session.post.assert_called_once_with(
        "https://app.ynab.com/api/v1/catalog",
        data={"operation_name": "syncBudgetData", "request_data": ANY},
        headers={
            "Accept": ANY,
            "Content-Type": ANY,
            "X-Requested-With": ANY,
            "X-YNAB-Client-Request-Id": ANY,
            "X-YNAB-Api-Version": ANY,
            "X-YNAB-Device-Id": ANY,
            "X-YNAB-Device-OS": ANY,
            "X-Session-Token": "token-value",
            "Cookie": "cookie-value",
        },
    )

    _, kwargs = fake_session.post.call_args
    request_data = json.loads(kwargs["data"]["request_data"])
    assert request_data["budget_version_id"] == "plan-1"
    assert request_data["starting_device_knowledge"] == 5
    assert request_data["ending_device_knowledge"] == 7
    assert request_data["device_knowledge_of_server"] == 7019

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
    fake_response, expected_substrings, subtests
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
        with subtests.test(substring=substring):
            assert substring in str(excinfo.value)
