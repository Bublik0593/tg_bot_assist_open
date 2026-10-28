from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..db import repo
from ..keyboards import BTN_SETTINGS
from ..services.scheduler import HabitScheduler
from ..states import TzManual
from ..utils import show

router = Router()

ZONES = [
    ("Калининград", "Europe/Kaliningrad"), ("Москва", "Europe/Moscow"), ("Самара", "Europe/Samara"),
    ("Екатеринбург", "Asia/Yekaterinburg"), ("Омск", "Asia/Omsk"), ("Новосибирск", "Asia/Novosibirsk"),
    ("Красноярск", "Asia/Krasnoyarsk"), ("Иркутск", "Asia/Irkutsk"), ("Якутск", "Asia/Yakutsk"),
    ("Владивосток", "Asia/Vladivostok"), ("Магадан", "Asia/Magadan"), ("Камчатка", "Asia/Kamchatka"),
]


def tz_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(ZONES), 2):
        rows.append([InlineKeyboardButton(text=ZONES[j][0], callback_data=f"tz:{j}") for j in range(i, i + 2)])
    rows.append([InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="tz:manual")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == BTN_SETTINGS)
async def settings(message: Message, tz: str):
    await message.answer(f"Текущий часовой пояс: <b>{tz}</b>\nВыберите новый:", reply_markup=tz_keyboard())


async def _apply(user_id: int, tz: str, db, scheduler: HabitScheduler):
    await repo.set_timezone(db, user_id, tz)
    await scheduler.sync_user(user_id)


@router.callback_query(F.data.regexp(r"^tz:\d+$"))
async def pick_zone(call: CallbackQuery, db, scheduler: HabitScheduler):
    idx = int(call.data.split(":")[1])
    if idx >= len(ZONES):
        return await call.answer()
    name, tz = ZONES[idx]
    await _apply(call.from_user.id, tz, db, scheduler)
    await show(call, f"Часовой пояс: <b>{name}</b> ({tz}). Напоминания перенастроены.")


@router.callback_query(F.data == "tz:manual")
async def manual(call: CallbackQuery, state: FSMContext):
    await state.set_state(TzManual.name)
    await show(call, "Введите название зоны IANA, например <code>Europe/Moscow</code> или <code>Asia/Tbilisi</code>.\n/cancel — отмена")


@router.message(TzManual.name, F.text)
async def manual_value(message: Message, state: FSMContext, db, scheduler: HabitScheduler):
    name = message.text.strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return await message.answer("Не знаю такой зоны. Пример: <code>Europe/Moscow</code>. Попробуйте ещё раз или /cancel.")
    await _apply(message.from_user.id, name, db, scheduler)
    await state.clear()
    await message.answer(f"Часовой пояс: <b>{name}</b>. Напоминания перенастроены.")
