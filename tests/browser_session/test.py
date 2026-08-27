import sqlite3
from unittest.mock import patch

import pytest

from manager_for_ynab._browser_session import _ENV_COOKIE
from manager_for_ynab._browser_session import _ENV_SESSION_TOKEN
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


def test_read_cookies_from_db_filters_by_host(tmp_path):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(
        db_path,
        [
            (".app.ynab.com", "_ynab_api_session", "abc"),
            ("app.ynab.com", "ys", "def"),
            ("example.com", "other", "ghi"),
        ],
    )

    assert _read_cookies_from_db(db_path) == {"_ynab_api_session": "abc", "ys": "def"}


def test_find_browser_cookie_header_returns_none_without_profiles(tmp_path):
    with patch(
        "manager_for_ynab._browser_session._firefox_cookie_db_paths",
        return_value=[],
    ):
        assert find_browser_cookie_header() is None


def test_find_browser_cookie_header_joins_cookies(tmp_path):
    db_path = tmp_path / "cookies.sqlite"
    _create_cookie_db(
        db_path, [(".app.ynab.com", "a", "1"), (".app.ynab.com", "b", "2")]
    )

    with patch(
        "manager_for_ynab._browser_session._firefox_cookie_db_paths",
        return_value=[db_path],
    ):
        assert find_browser_cookie_header() == "a=1; b=2"


def test_find_browser_cookie_header_skips_unreadable_db(tmp_path):
    bad_db = tmp_path / "bad.sqlite"
    bad_db.write_text("not a sqlite file")
    good_db = tmp_path / "good.sqlite"
    _create_cookie_db(good_db, [(".app.ynab.com", "a", "1")])

    with patch(
        "manager_for_ynab._browser_session._firefox_cookie_db_paths",
        return_value=[bad_db, good_db],
    ):
        assert find_browser_cookie_header() == "a=1"


def test_resolve_session_cookie_prefers_override():
    assert resolve_session_cookie("override") == "override"


@patch.dict("os.environ", {_ENV_COOKIE: "from-env"})
def test_resolve_session_cookie_uses_env_var():
    assert resolve_session_cookie() == "from-env"


@patch.dict("os.environ", {}, clear=True)
@patch(
    "manager_for_ynab._browser_session.find_browser_cookie_header",
    return_value="from-browser",
)
def test_resolve_session_cookie_falls_back_to_browser(find_cookie_header):
    assert resolve_session_cookie() == "from-browser"


@patch.dict("os.environ", {}, clear=True)
@patch(
    "manager_for_ynab._browser_session.find_browser_cookie_header", return_value=None
)
def test_resolve_session_cookie_raises_when_nothing_found(find_cookie_header):
    with pytest.raises(ValueError) as excinfo:
        resolve_session_cookie()

    assert _ENV_COOKIE in str(excinfo.value)


def test_resolve_session_token_prefers_override():
    assert resolve_session_token("override") == "override"


@patch.dict("os.environ", {_ENV_SESSION_TOKEN: "from-env"})
def test_resolve_session_token_uses_env_var():
    assert resolve_session_token() == "from-env"


@patch.dict("os.environ", {}, clear=True)
def test_resolve_session_token_raises_when_missing():
    with pytest.raises(ValueError) as excinfo:
        resolve_session_token()

    assert _ENV_SESSION_TOKEN in str(excinfo.value)
