from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..keyboards import main_menu

router = Router()

HELP = (
    "<b>Что умеет бот</b>\n\n"
    "✅ <b>Привычки</b> — задайте дни и время, бот напомнит и построит таблицу выполнения.\n"
    "🎯 <b>Цели</b> — список целей с отметкой выполнения.\n"
    "📚 <b>Книги</b> — отправьте файл .txt, .docx или .pdf, и он появится в списке. Прогресс чтения сохраняется.\n"
    "⚙️ <b>Настройки</b> — часовой пояс (по умолчанию Москва).\n\n"
    "/cancel — отменить текущее действие."
)


@router.message(CommandStart())
async def start(message: Message, tz: str):
    await message.answer(
        f"Привет! Я помогу с привычками, целями и чтением книг.\nЧасовой пояс: <b>{tz}</b> (меняется в настройках).\n\n{HELP}",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def help_(message: Message):
    await message.answer(HELP, reply_markup=main_menu())


@router.message(Command("cancel"))
async def cancel(message: Message):
    await message.answer("Отменено.", reply_markup=main_menu())
