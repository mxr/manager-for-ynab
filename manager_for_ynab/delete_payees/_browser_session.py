from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from manager_for_ynab.delete_payees._session_token_store import load_session_token
from manager_for_ynab.delete_payees._session_token_store import save_session_token

if TYPE_CHECKING:
    from playwright._impl._api_structures import SetCookieParam
    from playwright.async_api import BrowserType

_APEX_COOKIE_DOMAIN = "ynab.com"
_SESSION_TOKEN_HEADER = "x-session-token"
_BROWSER_CAPTURE_TIMEOUT_SECONDS = 300
# Must match the real Firefox that owns the session cookie being seeded below - a
# cookie showing up from a different User-Agent than the one that created it reads
# as session hijacking to YNAB's fraud check. Update if your Firefox version moves.
_FIREFOX_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:155.0) "
    "Gecko/20100101 Firefox/155.0"
)


def _firefox_profile_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / "Library" / "Application Support" / "Firefox" / "Profiles",  # macOS
        home / ".mozilla" / "firefox",  # Linux
    )


def _firefox_cookie_db_paths() -> list[Path]:
    return sorted(
        path
        for root in _firefox_profile_roots()
        if root.is_dir()
        for path in root.glob("*/cookies.sqlite")
    )


def _is_unreadable_dir(path: Path) -> bool:
    try:
        os.listdir(path)
    except PermissionError:
        return True
    except OSError:
        return False
    return False


async def _read_session_cookie_value(db_path: Path) -> str | None:
    # Firefox holds cookies.sqlite open while running, so copy it before reading.
    # Recent writes (e.g. a fresh login) may only be in the WAL, so copy that too.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_copy = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db_path, tmp_copy)
        wal_path = db_path.with_name(f"{db_path.name}-wal")
        if wal_path.exists():
            shutil.copy2(wal_path, tmp_copy.with_name(f"{tmp_copy.name}-wal"))
        async with aiosqlite.connect(tmp_copy) as con:
            cur = await con.execute(
                "SELECT value FROM moz_cookies "
                "WHERE host = 'app.ynab.com' AND name = '_ynab_api_session'"
            )
            row = await cur.fetchone()
            return str(row[0]) if row is not None else None


async def find_browser_cookie_header() -> str | None:
    for db_path in _firefox_cookie_db_paths():
        try:
            value = await _read_session_cookie_value(db_path)
        except aiosqlite.Error:
            continue
        if value is not None:
            return f"_ynab_api_session={value}"
    return None


async def resolve_session_cookie() -> str:
    cookie = await find_browser_cookie_header()
    if cookie is not None:
        return cookie

    # Path.glob silently yields nothing for a dir we can't read (e.g. macOS
    # blocking the terminal from Firefox's data), so check for that explicitly.
    if unreadable := [
        root for root in _firefox_profile_roots() if _is_unreadable_dir(root)
    ]:
        app = os.environ.get("TERM_PROGRAM", "your terminal app")
        raise ValueError(
            f"Permission denied reading Firefox profiles at {unreadable[0]}. Allow {app} to access data from Firefox in System Settings > Privacy & Security, then restart {app}."
        )

    if not _firefox_cookie_db_paths():
        roots = " or ".join(str(root) for root in _firefox_profile_roots())
        raise ValueError(
            f"No Firefox profile with a cookies.sqlite found under {roots}. Install Firefox and log into app.ynab.com."
        )

    raise ValueError(
        "Must be logged into app.ynab.com in Firefox so the session cookie can be "
        "read from your cookie jar."
    )


async def _ensure_playwright_firefox_installed(firefox: BrowserType) -> None:
    if Path(firefox.executable_path).exists():
        return

    print("Playwright's Firefox build isn't installed. Installing it now...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "playwright", "install", "firefox"
    )
    ret = await proc.wait()
    if ret != 0:
        raise RuntimeError(f"'playwright install firefox' failed with exit code {ret}.")


def _cookie_header_to_playwright_cookies(cookie: str) -> list[SetCookieParam]:
    return [
        {"name": name, "value": value, "domain": f".{_APEX_COOKIE_DOMAIN}", "path": "/"}
        for name, _, value in (pair.partition("=") for pair in cookie.split("; "))
    ]


async def capture_session_token_via_browser(
    *, cookie: str, timeout: float = _BROWSER_CAPTURE_TIMEOUT_SECONDS
) -> str:
    # Playwright inspects event-handler signatures at runtime (even under Python
    # 3.14's lazy annotations), so Request must be a real import, not a
    # TYPE_CHECKING-only one. Importing playwright lazily here (instead of at
    # module level) keeps it an optional dependency (the "delete-payees" extra).
    from playwright.async_api import Request
    from playwright.async_api import async_playwright

    token_future = asyncio.Future[str]()

    def _on_request(request: Request) -> None:
        if token_future.done():
            return
        value = request.headers.get(_SESSION_TOKEN_HEADER, "")
        if value:
            token_future.set_result(value)

    async with async_playwright() as playwright:
        await _ensure_playwright_firefox_installed(playwright.firefox)
        async with await playwright.firefox.launch(headless=False) as browser:
            context = await browser.new_context(user_agent=_FIREFOX_USER_AGENT)
            await context.add_cookies(_cookie_header_to_playwright_cookies(cookie))
            page = await context.new_page()
            page.on("request", _on_request)
            await page.goto("https://app.ynab.com/")
            return await asyncio.wait_for(token_future, timeout=timeout)


async def resolve_session_token(*, db: Path, cookie: str) -> str:
    stored = await load_session_token(db)
    if stored is not None:
        return stored

    try:
        token = await capture_session_token_via_browser(cookie=cookie)
    except TimeoutError as err:
        raise ValueError(
            "Timed out waiting for app.ynab.com to make a request carrying "
            "X-Session-Token. Check the opened browser window loaded app.ynab.com "
            "successfully."
        ) from err
    await save_session_token(db, token)
    return token


__all__ = [
    "capture_session_token_via_browser",
    "find_browser_cookie_header",
    "resolve_session_cookie",
    "resolve_session_token",
]
