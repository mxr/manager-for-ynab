import json
import sqlite3
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
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
from manager_for_ynab.delete_payees._browser_session import _ENV_SESSION_TOKEN
from manager_for_ynab.delete_payees._browser_session import _firefox_cookie_db_paths
from manager_for_ynab.delete_payees._browser_session import _read_cookies_from_db
from manager_for_ynab.delete_payees._browser_session import find_browser_cookie_header
from manager_for_ynab.delete_payees._browser_session import resolve_session_cookie
from manager_for_ynab.delete_payees._browser_session import resolve_session_token
from manager_for_ynab.delete_payees._ynab_sync_api import delete_payee
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


def _create_cookie_db(path, cookies):
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT)")
        con.executemany(
            "INSERT INTO moz_cookies (host, name, value) VALUES (?, ?, ?)", cookies
        )


@pytest.mark.asyncio
async def test_read_cookies_from_db_filters_by_host(tmp_path):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(
        db_path,
        [
            (".app.ynab.com", "_ynab_api_session", "abc"),
            ("app.ynab.com", "ys", "def"),
            ("example.com", "other", "ghi"),
        ],
    )

    assert await _read_cookies_from_db(db_path) == {
        "_ynab_api_session": "abc",
        "ys": "def",
    }


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
async def test_find_browser_cookie_header_joins_cookies(db_paths_mock, tmp_path):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(
        db_path, [(".app.ynab.com", "a", "1"), (".app.ynab.com", "b", "2")]
    )
    db_paths_mock.return_value = [db_path]

    assert await find_browser_cookie_header() == "a=1; b=2"


@patch("manager_for_ynab.delete_payees._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_skips_unreadable_db(db_paths_mock, tmp_path):
    bad_db = tmp_path / "bad.sqlite"
    bad_db.write_text("not a sqlite file")
    good_db = tmp_path / "good.sqlite"
    _create_cookie_db(good_db, [(".app.ynab.com", "a", "1")])
    db_paths_mock.return_value = [bad_db, good_db]

    assert await find_browser_cookie_header() == "a=1"


@patch("manager_for_ynab.delete_payees._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_skips_db_with_no_matching_cookies(
    db_paths_mock, tmp_path
):
    empty_db = tmp_path / "empty.sqlite"
    _create_cookie_db(empty_db, [("example.com", "a", "1")])
    good_db = tmp_path / "good.sqlite"
    _create_cookie_db(good_db, [(".app.ynab.com", "b", "2")])
    db_paths_mock.return_value = [empty_db, good_db]

    assert await find_browser_cookie_header() == "b=2"


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


@pytest.mark.session_token_env("from-env")
def test_resolve_session_token_uses_env_var():
    assert resolve_session_token() == "from-env"


@pytest.mark.session_token_env(None)
def test_resolve_session_token_raises_when_missing():
    with pytest.raises(ValueError) as excinfo:
        resolve_session_token()

    assert _ENV_SESSION_TOKEN in str(excinfo.value)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_delete_payee_sends_tombstone_delta():
    fake_session = MagicMock()
    fake_session.post = MagicMock(
        return_value=_FakeResponse({"error": None, "current_server_knowledge": 7020})
    )

    result = await delete_payee(
        fake_session,
        cookie="cookie-value",
        session_token="token-value",
        budget_version_id="plan-1",
        payee_id="payee-1",
        payee_name="Amazon Duplicate",
        starting_device_knowledge=5,
        ending_device_knowledge=6,
        device_knowledge_of_server=7019,
    )

    assert result == {"error": None, "current_server_knowledge": 7020}
    fake_session.post.assert_called_once()

    _, kwargs = fake_session.post.call_args
    request_data = json.loads(kwargs["data"]["request_data"])
    assert request_data["budget_version_id"] == "plan-1"
    assert request_data["starting_device_knowledge"] == 5
    assert request_data["ending_device_knowledge"] == 6
    assert request_data["device_knowledge_of_server"] == 7019
    assert kwargs["headers"]["Cookie"] == "cookie-value"
    assert kwargs["headers"]["X-Session-Token"] == "token-value"

    payee_entity = request_data["changed_entities"]["be_payees"][0]
    assert payee_entity["id"] == "payee-1"
    assert payee_entity["is_tombstone"] is True
    assert payee_entity["name"] == "Amazon Duplicate"


@pytest.mark.asyncio
async def test_delete_payee_raises_on_error_response():
    fake_session = MagicMock()
    fake_session.post = MagicMock(
        return_value=_FakeResponse({"error": "not authorized"})
    )

    with pytest.raises(RuntimeError) as excinfo:
        await delete_payee(
            fake_session,
            cookie="cookie-value",
            session_token="token-value",
            budget_version_id="plan-1",
            payee_id="payee-1",
            payee_name="Amazon Duplicate",
            starting_device_knowledge=0,
            ending_device_knowledge=1,
            device_knowledge_of_server=0,
        )

    assert "not authorized" in str(excinfo.value)
