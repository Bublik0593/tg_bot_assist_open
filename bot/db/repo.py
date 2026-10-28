"""Запросы к БД. Все выборки пользовательских данных фильтруются по user_id."""
from .database import Database


# ---------- users ----------
async def ensure_user(db: Database, tg_id: int, default_tz: str) -> str:
    await db.execute("INSERT OR IGNORE INTO users (tg_id, timezone) VALUES (?, ?)", (tg_id, default_tz))
    row = await db.fetchone("SELECT timezone FROM users WHERE tg_id = ?", (tg_id,))
    return row["timezone"]


async def set_timezone(db: Database, tg_id: int, tz: str) -> None:
    await db.execute("UPDATE users SET timezone = ? WHERE tg_id = ?", (tz, tg_id))


# ---------- goals ----------
async def add_goal(db: Database, user_id: int, title: str, description: str) -> int:
    return await db.execute(
        "INSERT INTO goals (user_id, title, description) VALUES (?, ?, ?)", (user_id, title, description)
    )


async def list_goals(db: Database, user_id: int, flt: str):
    where = {"open": "AND is_done = 0", "done": "AND is_done = 1"}.get(flt, "")
    return await db.fetchall(
        f"SELECT * FROM goals WHERE user_id = ? {where} ORDER BY is_done, id DESC", (user_id,)
    )


async def get_goal(db: Database, user_id: int, goal_id: int):
    return await db.fetchone("SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))


async def toggle_goal(db: Database, user_id: int, goal_id: int) -> None:
    await db.execute(
        """UPDATE goals SET is_done = 1 - is_done,
               done_at = CASE WHEN is_done = 0 THEN datetime('now') ELSE NULL END
           WHERE id = ? AND user_id = ?""",
        (goal_id, user_id),
    )


async def rename_goal(db: Database, user_id: int, goal_id: int, title: str) -> None:
    await db.execute("UPDATE goals SET title = ? WHERE id = ? AND user_id = ?", (title, goal_id, user_id))


async def delete_goal(db: Database, user_id: int, goal_id: int) -> None:
    await db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))


# ---------- habits ----------
async def add_habit(db: Database, user_id: int, name: str, weekdays: str, time: str, created_date: str) -> int:
    return await db.execute(
        "INSERT INTO habits (user_id, name, weekdays, time, created_date) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, weekdays, time, created_date),
    )


async def list_habits(db: Database, user_id: int):
    return await db.fetchall("SELECT * FROM habits WHERE user_id = ? ORDER BY time, id", (user_id,))


async def get_habit(db: Database, user_id: int, habit_id: int):
    return await db.fetchone("SELECT * FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id))


async def get_habit_with_tz(db: Database, habit_id: int):
    """Для планировщика: привычка + часовой пояс владельца."""
    return await db.fetchone(
        "SELECT h.*, u.timezone FROM habits h JOIN users u ON u.tg_id = h.user_id WHERE h.id = ?", (habit_id,)
    )


async def list_active_habits_with_tz(db: Database, user_id: int | None = None):
    sql = "SELECT h.*, u.timezone FROM habits h JOIN users u ON u.tg_id = h.user_id WHERE h.is_active = 1"
    params: tuple = ()
    if user_id is not None:
        sql += " AND h.user_id = ?"
        params = (user_id,)
    return await db.fetchall(sql, params)


async def toggle_habit_active(db: Database, user_id: int, habit_id: int) -> None:
    await db.execute("UPDATE habits SET is_active = 1 - is_active WHERE id = ? AND user_id = ?", (habit_id, user_id))


async def delete_habit(db: Database, user_id: int, habit_id: int) -> None:
    await db.execute("DELETE FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id))


async def set_habit_log(db: Database, habit_id: int, date: str, status: str) -> None:
    await db.execute(
        """INSERT INTO habit_logs (habit_id, date, status) VALUES (?, ?, ?)
           ON CONFLICT(habit_id, date) DO UPDATE SET status = excluded.status""",
        (habit_id, date, status),
    )


async def get_habit_log(db: Database, habit_id: int, date: str):
    return await db.fetchone("SELECT * FROM habit_logs WHERE habit_id = ? AND date = ?", (habit_id, date))


async def list_logs(db: Database, user_id: int, since: str):
    return await db.fetchall(
        """SELECT l.habit_id, l.date, l.status FROM habit_logs l
           JOIN habits h ON h.id = l.habit_id
           WHERE h.user_id = ? AND l.date >= ?""",
        (user_id, since),
    )


# ---------- books ----------
async def add_book(db: Database, user_id: int, title: str, file_name: str, pages: list[str]) -> int:
    async with db.tx() as c:
        cur = await c.execute(
            "INSERT INTO books (user_id, title, file_name, total_pages) VALUES (?, ?, ?, ?)",
            (user_id, title, file_name, len(pages)),
        )
        book_id = cur.lastrowid
        await c.executemany(
            "INSERT INTO book_pages (book_id, page_no, text) VALUES (?, ?, ?)",
            [(book_id, i, t) for i, t in enumerate(pages, start=1)],
        )
    return book_id


async def list_books(db: Database, user_id: int):
    return await db.fetchall(
        """SELECT b.id, b.title, b.total_pages, COALESCE(p.current_page, 1) AS current_page
           FROM books b LEFT JOIN reading_progress p ON p.book_id = b.id AND p.user_id = b.user_id
           WHERE b.user_id = ? ORDER BY COALESCE(p.updated_at, b.uploaded_at) DESC""",
        (user_id,),
    )


async def get_book(db: Database, user_id: int, book_id: int):
    return await db.fetchone(
        """SELECT b.id, b.title, b.total_pages, COALESCE(p.current_page, 1) AS current_page
           FROM books b LEFT JOIN reading_progress p ON p.book_id = b.id AND p.user_id = b.user_id
           WHERE b.id = ? AND b.user_id = ?""",
        (book_id, user_id),
    )


async def get_page(db: Database, user_id: int, book_id: int, page_no: int):
    """Текст страницы; None, если книга чужая или страницы нет."""
    row = await db.fetchone(
        """SELECT bp.text FROM book_pages bp JOIN books b ON b.id = bp.book_id
           WHERE bp.book_id = ? AND bp.page_no = ? AND b.user_id = ?""",
        (book_id, page_no, user_id),
    )
    return row["text"] if row else None


async def save_progress(db: Database, user_id: int, book_id: int, page_no: int) -> None:
    await db.execute(
        """INSERT INTO reading_progress (user_id, book_id, current_page) VALUES (?, ?, ?)
           ON CONFLICT(user_id, book_id) DO UPDATE
           SET current_page = excluded.current_page, updated_at = datetime('now')""",
        (user_id, book_id, page_no),
    )


async def delete_book(db: Database, user_id: int, book_id: int) -> None:
    await db.execute("DELETE FROM books WHERE id = ? AND user_id = ?", (book_id, user_id))
