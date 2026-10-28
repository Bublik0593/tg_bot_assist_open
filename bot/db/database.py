import asyncio
import os
from contextlib import asynccontextmanager

import aiosqlite

MIGRATIONS = [
    """
    CREATE TABLE users (
        tg_id      INTEGER PRIMARY KEY,
        timezone   TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE habits (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
        name         TEXT NOT NULL,
        weekdays     TEXT NOT NULL,           -- "0,2,4", Пн=0
        time         TEXT NOT NULL,           -- "HH:MM" локальное время пользователя
        is_active    INTEGER NOT NULL DEFAULT 1,
        created_date TEXT NOT NULL            -- локальная дата создания (ISO)
    );
    CREATE INDEX idx_habits_user ON habits(user_id);
    CREATE TABLE habit_logs (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
        date     TEXT NOT NULL,
        status   TEXT NOT NULL CHECK (status IN ('done','skipped')),
        UNIQUE (habit_id, date)
    );
    CREATE TABLE goals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
        title       TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        is_done     INTEGER NOT NULL DEFAULT 0,
        done_at     TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_goals_user ON goals(user_id, is_done);
    CREATE TABLE books (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
        title       TEXT NOT NULL,
        file_name   TEXT NOT NULL,
        total_pages INTEGER NOT NULL,
        uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_books_user ON books(user_id);
    CREATE TABLE book_pages (
        book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        page_no INTEGER NOT NULL,
        text    TEXT NOT NULL,
        PRIMARY KEY (book_id, page_no)
    );
    CREATE TABLE reading_progress (
        user_id      INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
        book_id      INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        current_page INTEGER NOT NULL,
        updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, book_id)
    );
    """,
]


class Database:
    """Одно соединение aiosqlite; все операции сериализуются блокировкой."""

    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self._migrate()

    async def _migrate(self) -> None:
        await self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        cur = await self.conn.execute("SELECT MAX(version) FROM schema_version")
        current = (await cur.fetchone())[0] or 0
        for i, sql in enumerate(MIGRATIONS[current:], start=current + 1):
            await self.conn.executescript(sql)
            await self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
            await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def fetchone(self, sql: str, params=()):
        async with self.lock:
            cur = await self.conn.execute(sql, params)
            return await cur.fetchone()

    async def fetchall(self, sql: str, params=()):
        async with self.lock:
            cur = await self.conn.execute(sql, params)
            return await cur.fetchall()

    async def execute(self, sql: str, params=()) -> int:
        """Выполняет запись и коммитит. Возвращает lastrowid."""
        async with self.lock:
            try:
                cur = await self.conn.execute(sql, params)
                await self.conn.commit()
                return cur.lastrowid
            except Exception:
                await self.conn.rollback()
                raise

    @asynccontextmanager
    async def tx(self):
        """Атомарная транзакция из нескольких запросов."""
        async with self.lock:
            try:
                yield self.conn
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise
