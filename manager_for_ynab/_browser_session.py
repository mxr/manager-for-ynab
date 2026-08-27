import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

_ENV_COOKIE = "YNAB_SESSION_COOKIE"
_ENV_SESSION_TOKEN = "YNAB_SESSION_TOKEN"
_COOKIE_DOMAIN = "app.ynab.com"


def _firefox_cookie_db_paths() -> list[Path]:
    home = Path.home()
    profile_roots = (
        home / "Library" / "Application Support" / "Firefox" / "Profiles",  # macOS
        home / ".mozilla" / "firefox",  # Linux
    )
    return sorted(
        path
        for root in profile_roots
        if root.is_dir()
        for path in root.glob("*/cookies.sqlite")
    )


def _read_cookies_from_db(db_path: Path) -> dict[str, str]:
    # Firefox holds cookies.sqlite open while running, so copy it before reading.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_copy = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db_path, tmp_copy)
        con = sqlite3.connect(tmp_copy)
        try:
            cur = con.execute(
                "SELECT name, value FROM moz_cookies WHERE host = ? OR host = ?",
                (_COOKIE_DOMAIN, f".{_COOKIE_DOMAIN}"),
            )
            return {name: value for name, value in cur.fetchall()}
        finally:
            con.close()


def find_browser_cookie_header() -> str | None:
    for db_path in _firefox_cookie_db_paths():
        try:
            cookies = _read_cookies_from_db(db_path)
        except sqlite3.Error:
            continue
        if cookies:
            return "; ".join(f"{name}={value}" for name, value in cookies.items())
    return None


def resolve_session_cookie(cookie_override: str | None = None) -> str:
    cookie = cookie_override or os.environ.get(_ENV_COOKIE)
    if cookie:
        return cookie

    cookie = find_browser_cookie_header()
    if cookie:
        return cookie

    raise ValueError(
        f"Must set app.ynab.com session cookie as {_ENV_COOKIE!r} environment variable, "
        "or be logged into app.ynab.com in Firefox so it can be read from your cookie jar."
    )


def resolve_session_token(token_override: str | None = None) -> str:
    token = token_override or os.environ.get(_ENV_SESSION_TOKEN)
    if token:
        return token

    raise ValueError(
        f"Must set app.ynab.com session token as {_ENV_SESSION_TOKEN!r} environment "
        "variable. Copy the 'X-Session-Token' request header from a logged-in "
        "app.ynab.com browser tab's network tab (any XHR request to /api/v1/catalog) "
        "- it isn't stored as a cookie so it can't be read automatically."
    )


__all__ = [
    "_ENV_COOKIE",
    "_ENV_SESSION_TOKEN",
    "find_browser_cookie_header",
    "resolve_session_cookie",
    "resolve_session_token",
]
