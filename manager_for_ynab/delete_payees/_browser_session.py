from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from manager_for_ynab.delete_payees._session_token_store import WebSession
from manager_for_ynab.delete_payees._session_token_store import load_web_session
from manager_for_ynab.delete_payees._session_token_store import save_web_session

if TYPE_CHECKING:
    from playwright.async_api import BrowserType

_YNAB_URL = "https://app.ynab.com/"
_SESSION_COOKIE_NAME = "_ynab_api_session"
_SESSION_TOKEN_HEADER = "x-session-token"
_BROWSER_CAPTURE_TIMEOUT_SECONDS = 300


def _browser_profile_dir(session_token_db: Path) -> Path:
    return session_token_db.parent / "browser-profile"


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


async def capture_web_session_via_browser(
    *, profile_dir: Path, timeout: float = _BROWSER_CAPTURE_TIMEOUT_SECONDS
) -> WebSession:
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
        # A dedicated profile keeps the login separate from the user's own
        # browser, so nothing needs permission to read another app's data.
        async with await playwright.firefox.launch_persistent_context(
            profile_dir, headless=False
        ) as context:
            page = await context.new_page()
            page.on("request", _on_request)
            await page.goto(_YNAB_URL)
            print("Log into app.ynab.com in the opened browser window if prompted.")
            token = await asyncio.wait_for(token_future, timeout=timeout)
            cookies = await context.cookies(_YNAB_URL)

    value = next(
        (c.get("value") for c in cookies if c.get("name") == _SESSION_COOKIE_NAME), None
    )
    if value is None:
        raise ValueError(f"app.ynab.com didn't set the {_SESSION_COOKIE_NAME} cookie.")
    return WebSession(cookie=f"{_SESSION_COOKIE_NAME}={value}", token=token)


async def resolve_web_session(*, db: Path) -> WebSession:
    stored = await load_web_session(db)
    if stored is not None:
        return stored

    try:
        web_session = await capture_web_session_via_browser(
            profile_dir=_browser_profile_dir(db)
        )
    except TimeoutError as err:
        raise ValueError(
            "Timed out waiting for app.ynab.com to make a request carrying "
            "X-Session-Token. Log into app.ynab.com in the opened browser window."
        ) from err
    await save_web_session(db, web_session)
    return web_session


__all__ = [
    "capture_web_session_via_browser",
    "resolve_web_session",
]
