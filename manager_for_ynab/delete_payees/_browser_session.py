import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

# Playwright inspects event-handler signatures at runtime (even under Python 3.14's
# lazy annotations), so Request must be a real import, not a TYPE_CHECKING-only one.
from playwright.async_api import Request  # noqa: TC002

from manager_for_ynab.delete_payees._session_token_store import load_session_token
from manager_for_ynab.delete_payees._session_token_store import save_session_token

if TYPE_CHECKING:
    from playwright._impl._api_structures import SetCookieParam
    from playwright.async_api import BrowserType

_ENV_SESSION_TOKEN = "YNAB_SESSION_TOKEN"
_COOKIE_DOMAIN = "app.ynab.com"
# The actual session cookie ("ys") is set on the apex domain, not app.ynab.com, so
# both must be read - app.ynab.com-only cookies are just analytics/tracking ones.
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


async def _read_cookies_from_db(db_path: Path) -> dict[str, str]:
    # Firefox holds cookies.sqlite open while running, so copy it before reading.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_copy = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db_path, tmp_copy)
        async with aiosqlite.connect(tmp_copy) as con:
            cur = await con.execute(
                "SELECT name, value FROM moz_cookies WHERE host IN (?, ?, ?, ?)",
                (
                    _COOKIE_DOMAIN,
                    f".{_COOKIE_DOMAIN}",
                    _APEX_COOKIE_DOMAIN,
                    f".{_APEX_COOKIE_DOMAIN}",
                ),
            )
            return {row[0]: row[1] for row in await cur.fetchall()}


async def find_browser_cookie_header() -> str | None:
    for db_path in _firefox_cookie_db_paths():
        try:
            cookies = await _read_cookies_from_db(db_path)
        except aiosqlite.Error:
            continue
        if cookies:
            return "; ".join(f"{name}={value}" for name, value in cookies.items())
    return None


async def resolve_session_cookie() -> str:
    cookie = await find_browser_cookie_header()
    if cookie:
        return cookie

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
    returncode = await proc.wait()
    if returncode != 0:
        raise RuntimeError(
            f"'playwright install firefox' failed with exit code {returncode}."
        )


def _cookie_header_to_playwright_cookies(cookie: str) -> list[SetCookieParam]:
    return [
        {"name": name, "value": value, "domain": f".{_APEX_COOKIE_DOMAIN}", "path": "/"}
        for name, _, value in (pair.partition("=") for pair in cookie.split("; "))
    ]


async def capture_session_token_via_browser(
    *, cookie: str, timeout: float = _BROWSER_CAPTURE_TIMEOUT_SECONDS
) -> str:
    # X-Session-Token is minted by app.ynab.com's own JS after login and never shows
    # up in a response body, so the only way to get it without a human copy-pasting
    # it is to drive a real browser and read it off an outgoing request. Seeding the
    # already-valid Firefox session cookie skips the login form entirely - actually
    # logging in from Playwright's browser (different fingerprint, no history) is
    # what trips YNAB's new-device/fraud check, not merely loading the app.
    from playwright.async_api import async_playwright

    token_future = asyncio.Future[str]()

    def _on_request(request: Request) -> None:
        if token_future.done():
            return
        value = request.headers.get(_SESSION_TOKEN_HEADER)
        if value:
            token_future.set_result(value)

    async with async_playwright() as playwright:
        await _ensure_playwright_firefox_installed(playwright.firefox)
        browser = await playwright.firefox.launch(headless=False)
        try:
            context = await browser.new_context(user_agent=_FIREFOX_USER_AGENT)
            await context.add_cookies(_cookie_header_to_playwright_cookies(cookie))
            page = await context.new_page()
            page.on("request", _on_request)
            await page.goto("https://app.ynab.com/")
            return await asyncio.wait_for(token_future, timeout=timeout)
        finally:
            await browser.close()


async def resolve_session_token(*, db: Path, cookie: str) -> str:
    token = os.environ.get(_ENV_SESSION_TOKEN)
    if token:
        return token

    stored = await load_session_token(db)
    if stored:
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
    "_ENV_SESSION_TOKEN",
    "capture_session_token_via_browser",
    "find_browser_cookie_header",
    "resolve_session_cookie",
    "resolve_session_token",
]
