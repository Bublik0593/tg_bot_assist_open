from datetime import date

import pytest

from bot.db import repo
from bot.db.database import Database
from bot.services.stats import build_table, streak


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    for uid in (1, 2):
        await repo.ensure_user(d, uid, "Europe/Moscow")
    yield d
    await d.close()


async def test_books_are_private_and_progress_saved(db):
    bid = await repo.add_book(db, 1, "Книга", "k.txt", ["p1", "p2", "p3"])
    assert await repo.get_page(db, 1, bid, 2) == "p2"
    # чужой пользователь ничего не видит и не может удалить
    assert await repo.get_book(db, 2, bid) is None
    assert await repo.get_page(db, 2, bid, 1) is None
    assert await repo.list_books(db, 2) == []
    await repo.delete_book(db, 2, bid)
    assert await repo.get_book(db, 1, bid) is not None
    # прогресс
    assert (await repo.get_book(db, 1, bid))["current_page"] == 1
    await repo.save_progress(db, 1, bid, 3)
    await repo.save_progress(db, 1, bid, 2)
    assert (await repo.list_books(db, 1))[0]["current_page"] == 2
    # каскадное удаление
    await repo.delete_book(db, 1, bid)
    assert await db.fetchone("SELECT 1 FROM book_pages") is None
    assert await db.fetchone("SELECT 1 FROM reading_progress") is None


async def test_goals_private_and_toggle(db):
    gid = await repo.add_goal(db, 1, "Цель", "")
    assert await repo.get_goal(db, 2, gid) is None
    await repo.toggle_goal(db, 2, gid)  # чужой — без эффекта
    assert not (await repo.get_goal(db, 1, gid))["is_done"]
    await repo.toggle_goal(db, 1, gid)
    g = await repo.get_goal(db, 1, gid)
    assert g["is_done"] and g["done_at"]
    assert len(await repo.list_goals(db, 1, "done")) == 1
    assert len(await repo.list_goals(db, 1, "open")) == 0
    await repo.toggle_goal(db, 1, gid)
    assert (await repo.get_goal(db, 1, gid))["done_at"] is None
    await repo.delete_goal(db, 2, gid)
    assert await repo.get_goal(db, 1, gid)


async def test_habits_private_logs_and_table(db):
    hid = await repo.add_habit(db, 1, "Зарядка", "0,1,2,3,4,5,6", "07:30", "2026-10-20")
    assert await repo.get_habit(db, 2, hid) is None
    await repo.set_habit_log(db, hid, "2026-10-26", "done")
    await repo.set_habit_log(db, hid, "2026-10-27", "done")
    await repo.set_habit_log(db, hid, "2026-10-27", "skipped")  # перезапись
    logs = {(r["habit_id"], r["date"]): r["status"] for r in await repo.list_logs(db, 1, "2026-10-01")}
    assert logs[(hid, "2026-10-27")] == "skipped"
    assert await repo.list_logs(db, 2, "2026-10-01") == []
    h = await repo.get_habit(db, 1, hid)
    today = date(2026, 10, 28)
    table = build_table([h], logs, today, 7)
    assert "✅" in table and "❌" in table and "⬜" in table and "➖" in table  # до создания — ➖
    assert streak(h, today, logs) == 0  # вчера пропущено
    await repo.set_habit_log(db, hid, "2026-10-28", "done")
    logs[(hid, "2026-10-28")] = "done"
    assert streak(h, today, logs) == 1
    await repo.delete_habit(db, 1, hid)
    assert await db.fetchone("SELECT 1 FROM habit_logs") is None
