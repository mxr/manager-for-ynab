import sqlite3
from unittest.mock import patch

import pytest

from manager_for_ynab._browser_session import _ENV_SESSION_TOKEN
from manager_for_ynab._browser_session import _firefox_cookie_db_paths
from manager_for_ynab._browser_session import _read_cookies_from_db
from manager_for_ynab._browser_session import find_browser_cookie_header
from manager_for_ynab._browser_session import resolve_session_cookie
from manager_for_ynab._browser_session import resolve_session_token


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


@patch("manager_for_ynab._browser_session.Path.home")
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


@patch("manager_for_ynab._browser_session.Path.home")
def test_firefox_cookie_db_paths_returns_empty_without_profile_dirs(
    home_mock, tmp_path
):
    home_mock.return_value = tmp_path
    assert _firefox_cookie_db_paths() == []


@patch(
    "manager_for_ynab._browser_session._firefox_cookie_db_paths",
    return_value=[],
)
@pytest.mark.asyncio
async def test_find_browser_cookie_header_returns_none_without_profiles(
    db_paths_mock, tmp_path
):
    assert await find_browser_cookie_header() is None


@patch("manager_for_ynab._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_joins_cookies(db_paths_mock, tmp_path):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(
        db_path, [(".app.ynab.com", "a", "1"), (".app.ynab.com", "b", "2")]
    )
    db_paths_mock.return_value = [db_path]

    assert await find_browser_cookie_header() == "a=1; b=2"


@patch("manager_for_ynab._browser_session._firefox_cookie_db_paths")
@pytest.mark.asyncio
async def test_find_browser_cookie_header_skips_unreadable_db(db_paths_mock, tmp_path):
    bad_db = tmp_path / "bad.sqlite"
    bad_db.write_text("not a sqlite file")
    good_db = tmp_path / "good.sqlite"
    _create_cookie_db(good_db, [(".app.ynab.com", "a", "1")])
    db_paths_mock.return_value = [bad_db, good_db]

    assert await find_browser_cookie_header() == "a=1"


@patch("manager_for_ynab._browser_session._firefox_cookie_db_paths")
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
    "manager_for_ynab._browser_session.find_browser_cookie_header",
    return_value="from-browser",
)
@pytest.mark.asyncio
async def test_resolve_session_cookie_reads_from_browser(find_cookie_header):
    assert await resolve_session_cookie() == "from-browser"


@patch(
    "manager_for_ynab._browser_session.find_browser_cookie_header", return_value=None
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
