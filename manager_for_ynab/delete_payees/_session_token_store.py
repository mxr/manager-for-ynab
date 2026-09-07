import os
from pathlib import Path

import aiosqlite

_PACKAGE = "manager-for-ynab"


def default_session_token_db_path() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / _PACKAGE / "session_token.sqlite"


async def load_session_token(db: Path) -> str | None:
    if not db.is_file():
        return None

    async with aiosqlite.connect(db) as con:
        cur = await con.execute("SELECT value FROM session_token WHERE id = 1")
        row = await cur.fetchone()
        return str(row[0]) if row else None


async def save_session_token(db: Path, token: str) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db) as con:
        await con.execute(
            "CREATE TABLE IF NOT EXISTS session_token (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        await con.execute(
            "INSERT INTO session_token (id, value) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET value = excluded.value",
            (token,),
        )
        await con.commit()


__all__ = [
    "default_session_token_db_path",
    "load_session_token",
    "save_session_token",
]
