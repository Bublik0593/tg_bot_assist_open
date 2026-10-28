from unittest.mock import AsyncMock

import pytest

from bot.db import repo
from bot.db.database import Database
from bot.services.scheduler import HabitScheduler


@pytest.fixture
async def env():
    db = Database(":memory:")
    await db.connect()
    await repo.ensure_user(db, 1, "Europe/Moscow")
    bot = AsyncMock()
    sch = HabitScheduler(bot, db)
    sch.sched.start()
    yield db, bot, sch
    sch.shutdown()
    await db.close()


async def test_job_lifecycle_and_timezone(env):
    db, bot, sch = env
    hid = await repo.add_habit(db, 1, "Бег", "0,2,4", "07:30", "2026-10-28")
    await sch.sync_habit(hid)
    job = sch.sched.get_job(f"habit:{hid}")
    assert job and str(job.trigger.timezone) == "Europe/Moscow"
    await repo.set_timezone(db, 1, "Asia/Vladivostok")
    await sch.sync_user(1)
    assert str(sch.sched.get_job(f"habit:{hid}").trigger.timezone) == "Asia/Vladivostok"
    await repo.toggle_habit_active(db, 1, hid)
    await sch.sync_habit(hid)
    assert sch.sched.get_job(f"habit:{hid}") is None
    await repo.toggle_habit_active(db, 1, hid)
    await sch.sync_habit(hid)
    sch.remove(hid)
    assert sch.sched.get_job(f"habit:{hid}") is None


async def test_notify_sends_once_unless_logged(env):
    db, bot, sch = env
    hid = await repo.add_habit(db, 1, "Бег", "0,1,2,3,4,5,6", "07:30", "2026-10-01")
    await sch._notify(hid)
    assert bot.send_message.await_count == 1
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    await repo.set_habit_log(db, hid, today, "done")
    await sch._notify(hid)
    assert bot.send_message.await_count == 1
