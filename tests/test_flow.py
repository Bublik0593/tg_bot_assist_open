"""Сквозной тест: реальные хендлеры + диспетчер, Telegram подменён."""
import importlib
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage, EditMessageText, AnswerCallbackQuery, GetFile
from aiogram.types import CallbackQuery, Chat, Document, File, Message, Update, User

from bot.config import Config
from bot.db import repo
from bot.db.database import Database
from bot.handlers import books, common, goals, habits, settings
from bot.middlewares import UserMiddleware
from bot.services.scheduler import HabitScheduler

BOOK = ("Это длинная книга для проверки. " * 400).encode("cp1251")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self): ...
    async def stream_content(self, *a, **k):
        yield BOOK
    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=1, type="private"), text=method.text).as_(bot)
        if isinstance(method, GetFile):
            return File(file_id="f", file_unique_id="u", file_path="x")
        return True


class Harness:
    def __init__(self, db, cfg):
        self.session = FakeSession()
        self.bot = Bot("1:abc", session=self.session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher(storage=MemoryStorage())
        self.sched = HabitScheduler(self.bot, db)
        self.dp["db"], self.dp["cfg"], self.dp["scheduler"] = db, cfg, self.sched
        mw = UserMiddleware(db, cfg.default_tz)
        self.dp.message.outer_middleware(mw)
        self.dp.callback_query.outer_middleware(mw)
        for m in (common, settings, goals, habits, books):
            self.dp.include_router(importlib.reload(m).router)  # свежий Router на каждый тест
        self.n = 0
        self.user = User(id=1, is_bot=False, first_name="T")
        self.chat = Chat(id=1, type="private")

    def _msg(self, **kw):
        self.n += 1
        return Message(message_id=self.n, date=datetime.now(), chat=self.chat, from_user=self.user, **kw)

    async def say(self, text):
        await self.dp.feed_update(self.bot, Update(update_id=self.n + 1000, message=self._msg(text=text)))

    async def click(self, data):
        self.n += 1
        cq = CallbackQuery(id=str(self.n), from_user=self.user, chat_instance="c", data=data,
                           message=self._msg(text="x"))
        await self.dp.feed_update(self.bot, Update(update_id=self.n + 1000, callback_query=cq))

    async def send_file(self, name, size=100):
        doc = Document(file_id="f", file_unique_id="u", file_name=name, file_size=size)
        await self.dp.feed_update(self.bot, Update(update_id=self.n + 1000, message=self._msg(document=doc)))

    def last_text(self):
        return [c.text for c in self.session.calls if isinstance(c, (SendMessage, EditMessageText))][-1]


@pytest.fixture
async def h():
    db = Database(":memory:")
    await db.connect()
    cfg = Config("1:abc", ":memory:", "Europe/Moscow", 1500, 10 * 1024 * 1024)
    hs = Harness(db, cfg)
    hs.sched.sched.start()
    yield hs
    hs.sched.shutdown()
    await db.close()


async def test_goals_flow(h):
    await h.say("/start")
    await h.say("🎯 Цели")
    await h.click("g:a")
    await h.say("Прочитать книгу")
    await h.say("-")
    goals_ = await repo.list_goals(h.dp["db"], 1, "open")
    assert [g["title"] for g in goals_] == ["Прочитать книгу"]
    await h.click(f"g:t:{goals_[0]['id']}:open")
    assert len(await repo.list_goals(h.dp["db"], 1, "done")) == 1
    await h.click("g:l:done")
    assert "Выполненные" in h.last_text()


async def test_habit_flow_and_marking(h):
    db = h.dp["db"]
    await h.say("✅ Привычки")
    await h.click("h:a")
    await h.say("Зарядка")
    await h.click("hd:wd")
    await h.click("hd:ok")
    await h.say("25:00")  # неверное время
    assert "Не понял" in h.last_text()
    await h.say("7:30")
    hab = (await repo.list_habits(db, 1))[0]
    assert hab["time"] == "07:30" and hab["weekdays"] == "0,1,2,3,4"
    assert h.sched.sched.get_job(f"habit:{hab['id']}")
    today = datetime.now().date().isoformat()
    await h.click(f"hl:done:{hab['id']}:{today}")
    assert (await repo.get_habit_log(db, hab["id"], today))["status"] == "done"
    await h.click("h:s:7")
    assert "Зарядка" in h.last_text()
    await h.click(f"h:dy:{hab['id']}")
    assert h.sched.sched.get_job(f"habit:{hab['id']}") is None


async def test_book_upload_read_progress(h):
    db = h.dp["db"]
    await h.send_file("notes.pdf")
    assert "только формат .txt" in h.last_text()
    await h.send_file("big.txt", size=50 * 1024 * 1024)
    assert "слишком большой" in h.last_text()
    await h.send_file("Война и мир.txt")
    book = (await repo.list_books(db, 1))[0]
    assert book["title"] == "Война и мир" and book["total_pages"] > 5
    await h.click(f"bk:o:{book['id']}")
    await h.click(f"bk:p:{book['id']}:3")
    assert "стр. 3/" in h.last_text()
    await h.say("📚 Книги")  # «выход» из книги
    assert (await repo.get_book(db, 1, book["id"]))["current_page"] == 3
    await h.click(f"bk:o:{book['id']}")  # повторное открытие
    assert "стр. 3/" in h.last_text()
    await h.click(f"bk:j:{book['id']}")
    await h.say("999")
    assert "Введите число" in h.last_text()
    await h.say("5")
    assert "стр. 5/" in h.last_text()


async def test_timezone_settings(h):
    await h.say("⚙️ Настройки")
    await h.click("tz:9")
    row = await h.dp["db"].fetchone("SELECT timezone FROM users WHERE tg_id=1")
    assert row["timezone"] == "Asia/Vladivostok"
    await h.click("tz:manual")
    await h.say("Mars/Olympus")
    assert "Не знаю" in h.last_text()
    await h.say("Asia/Tbilisi")
    row = await h.dp["db"].fetchone("SELECT timezone FROM users WHERE tg_id=1")
    assert row["timezone"] == "Asia/Tbilisi"
