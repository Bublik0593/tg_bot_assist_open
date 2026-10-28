import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import load_config
from bot.db.database import Database
from bot.handlers import books, common, goals, habits, settings
from bot.middlewares import UserMiddleware
from bot.services.scheduler import HabitScheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db = Database(cfg.db_path)
    await db.connect()

    bot = Bot(cfg.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = HabitScheduler(bot, db)

    dp = Dispatcher(storage=MemoryStorage())
    dp["db"], dp["cfg"], dp["scheduler"] = db, cfg, scheduler
    mw = UserMiddleware(db, cfg.default_tz)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    for r in (common.router, settings.router, goals.router, habits.router, books.router):
        dp.include_router(r)

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="cancel", description="Отменить действие"),
    ])
    await scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
