from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

_PACKAGE = "manager-for-ynab"


@dataclass(frozen=True, slots=True)
class WebSession:
    cookie: str
    token: str


def default_session_token_db_path() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / _PACKAGE / "session-token.sqlite"


async def load_web_session(db: Path) -> WebSession | None:
    if not db.is_file():
        return None

    async with aiosqlite.connect(db) as con:
        cur = await con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'web_session'"
        )
        if await cur.fetchone() is None:
            return None
        cur = await con.execute("SELECT cookie, token FROM web_session WHERE id = 1")
        row = await cur.fetchone()
        return (
            WebSession(cookie=str(row[0]), token=str(row[1]))
            if row is not None
            else None
        )


async def save_web_session(db: Path, web_session: WebSession) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db) as con:
        await con.execute(
            "CREATE TABLE IF NOT EXISTS web_session (id INTEGER PRIMARY KEY, cookie TEXT NOT NULL, token TEXT NOT NULL)"
        )
        await con.execute(
            "INSERT INTO web_session (id, cookie, token) VALUES (1, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET cookie = excluded.cookie, token = excluded.token",
            (web_session.cookie, web_session.token),
        )
        await con.commit()


__all__ = [
    "WebSession",
    "default_session_token_db_path",
    "load_web_session",
    "save_web_session",
]
