import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..db import repo
from ..db.database import Database
from .stats import parse_weekdays

log = logging.getLogger(__name__)
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def habit_keyboard(habit_id: int, day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Выполнил", callback_data=f"hl:done:{habit_id}:{day}"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"hl:skip:{habit_id}:{day}"),
        ]]
    )


class HabitScheduler:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.sched = AsyncIOScheduler(timezone="UTC")

    @staticmethod
    def _job_id(habit_id: int) -> str:
        return f"habit:{habit_id}"

    async def start(self) -> None:
        for h in await repo.list_active_habits_with_tz(self.db):
            self._add(h)
        self.sched.start()

    def shutdown(self) -> None:
        self.sched.shutdown(wait=False)

    def _add(self, h) -> None:
        hour, minute = map(int, h["time"].split(":"))
        days = ",".join(DAY_NAMES[d] for d in sorted(parse_weekdays(h["weekdays"])))
        if not days:
            return
        trigger = CronTrigger(day_of_week=days, hour=hour, minute=minute, timezone=ZoneInfo(h["timezone"]))
        self.sched.add_job(
            self._notify, trigger, args=[h["id"]], id=self._job_id(h["id"]),
            replace_existing=True, misfire_grace_time=300, coalesce=True,
        )

    def remove(self, habit_id: int) -> None:
        if self.sched.get_job(self._job_id(habit_id)):
            self.sched.remove_job(self._job_id(habit_id))

    async def sync_habit(self, habit_id: int) -> None:
        self.remove(habit_id)
        h = await repo.get_habit_with_tz(self.db, habit_id)
        if h and h["is_active"]:
            self._add(h)

    async def sync_user(self, user_id: int) -> None:
        for h in await repo.list_habits(self.db, user_id):
            await self.sync_habit(h["id"])

    async def _notify(self, habit_id: int) -> None:
        h = await repo.get_habit_with_tz(self.db, habit_id)
        if not h or not h["is_active"]:
            return
        today = datetime.now(ZoneInfo(h["timezone"])).date().isoformat()
        if await repo.get_habit_log(self.db, habit_id, today):
            return
        try:
            await self.bot.send_message(
                h["user_id"], f"⏰ Время привычки: <b>{html.escape(h['name'])}</b>",
                reply_markup=habit_keyboard(habit_id, today),
            )
        except TelegramAPIError as e:
            log.warning("Не удалось отправить уведомление habit=%s user=%s: %s", habit_id, h["user_id"], e)

