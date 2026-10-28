import html
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from ..db import repo
from ..keyboards import BTN_HABITS
from ..services.scheduler import HabitScheduler
from ..services.stats import WEEKDAYS_SHORT, build_table, parse_weekdays
from ..states import HabitAdd
from ..utils import short, show

router = Router()
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def days_label(weekdays: str) -> str:
    days = parse_weekdays(weekdays)
    if len(days) == 7:
        return "каждый день"
    return ",".join(WEEKDAYS_SHORT[d] for d in sorted(days))


async def render_list(target, db, user_id: int):
    habits = await repo.list_habits(db, user_id)
    rows = [
        [B(text=f"{'⏰' if h['is_active'] else '⏸'} {h['time']} {short(h['name'], 28)} · {days_label(h['weekdays'])}",
           callback_data=f"h:v:{h['id']}")]
        for h in habits
    ]
    rows.append([B(text="➕ Добавить", callback_data="h:a"), B(text="📊 Статистика", callback_data="h:s:7")])
    text = "✅ <b>Привычки</b>" + ("" if habits else "\nПока пусто.")
    await show(target, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text == BTN_HABITS)
async def menu(message: Message, db):
    await render_list(message, db, message.from_user.id)


@router.callback_query(F.data == "h:l")
async def back_to_list(call: CallbackQuery, db):
    await render_list(call, db, call.from_user.id)


# --- карточка ---
async def render_habit(call: CallbackQuery, db, habit_id: int):
    h = await repo.get_habit(db, call.from_user.id, habit_id)
    if not h:
        return await render_list(call, db, call.from_user.id)
    state = "активна" if h["is_active"] else "на паузе"
    text = f"<b>{html.escape(h['name'])}</b>\nДни: {days_label(h['weekdays'])}\nВремя: {h['time']}\nСтатус: {state}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="▶️ Возобновить" if not h["is_active"] else "⏸ Пауза", callback_data=f"h:p:{habit_id}"),
         B(text="🗑 Удалить", callback_data=f"h:d:{habit_id}")],
        [B(text="⬅️ К списку", callback_data="h:l")],
    ])
    await show(call, text, kb)


@router.callback_query(F.data.regexp(r"^h:v:\d+$"))
async def view(call: CallbackQuery, db):
    await render_habit(call, db, int(call.data.split(":")[2]))


@router.callback_query(F.data.regexp(r"^h:p:\d+$"))
async def pause(call: CallbackQuery, db, scheduler: HabitScheduler):
    hid = int(call.data.split(":")[2])
    await repo.toggle_habit_active(db, call.from_user.id, hid)
    await scheduler.sync_habit(hid)
    await render_habit(call, db, hid)


@router.callback_query(F.data.regexp(r"^h:d:\d+$"))
async def delete_ask(call: CallbackQuery):
    hid = call.data.split(":")[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        B(text="Да, удалить", callback_data=f"h:dy:{hid}"), B(text="Отмена", callback_data=f"h:v:{hid}"),
    ]])
    await show(call, "Удалить привычку вместе с историей выполнения?", kb)


@router.callback_query(F.data.regexp(r"^h:dy:\d+$"))
async def delete_yes(call: CallbackQuery, db, scheduler: HabitScheduler):
    hid = int(call.data.split(":")[2])
    await repo.delete_habit(db, call.from_user.id, hid)
    scheduler.remove(hid)
    await render_list(call, db, call.from_user.id)


# --- статистика ---
@router.callback_query(F.data.regexp(r"^h:s:(7|14)$"))
async def stats(call: CallbackQuery, db, tz: str):
    days = int(call.data.split(":")[2])
    today = datetime.now(ZoneInfo(tz)).date()
    habits = await repo.list_habits(db, call.from_user.id)
    since = date.fromordinal(today.toordinal() - 400).isoformat()  # хватает для серий
    logs = {(r["habit_id"], r["date"]): r["status"] for r in await repo.list_logs(db, call.from_user.id, since)}
    other = 14 if days == 7 else 7
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text=f"За {other} дней", callback_data=f"h:s:{other}")],
        [B(text="⬅️ К списку", callback_data="h:l")],
    ])
    await show(call, f"📊 <b>Выполнение за {days} дн.</b>\n" + build_table(habits, logs, today, days), kb)


# --- отметки из уведомлений ---
@router.callback_query(F.data.regexp(r"^hl:(done|skip):\d+:\d{4}-\d{2}-\d{2}$"))
async def mark(call: CallbackQuery, db, tz: str):
    _, action, hid, day = call.data.split(":")
    h = await repo.get_habit(db, call.from_user.id, int(hid))
    today = datetime.now(ZoneInfo(tz)).date()
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return await call.answer()
    if not h or d > today:
        return await call.answer("Привычка не найдена", show_alert=True)
    status = "done" if action == "done" else "skipped"
    await repo.set_habit_log(db, h["id"], day, status)
    icon = "✅ Выполнено" if status == "done" else "⏭ Пропущено"
    await show(call, f"{icon}: <b>{html.escape(h['name'])}</b> ({d.strftime('%d.%m')})")


# --- добавление ---
@router.callback_query(F.data == "h:a")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(HabitAdd.name)
    await show(call, "Название привычки? (/cancel — отмена)")


@router.message(HabitAdd.name, F.text)
async def add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) > 100:
        return await message.answer("Название должно быть от 1 до 100 символов.")
    await state.update_data(name=name, days=[])
    await state.set_state(HabitAdd.days)
    await message.answer("В какие дни напоминать?", reply_markup=days_keyboard(set()))


def days_keyboard(selected: set[int]) -> InlineKeyboardMarkup:
    row = [B(text=("✓ " if i in selected else "") + WEEKDAYS_SHORT[i], callback_data=f"hd:{i}") for i in range(7)]
    return InlineKeyboardMarkup(inline_keyboard=[
        row[:4], row[4:],
        [B(text="Каждый день", callback_data="hd:all"), B(text="Будни", callback_data="hd:wd")],
        [B(text="Готово ➡️", callback_data="hd:ok")],
    ])


@router.callback_query(HabitAdd.days, F.data.regexp(r"^hd:(\d|all|wd|ok)$"))
async def pick_days(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":")[1]
    sel = set((await state.get_data())["days"])
    if key == "ok":
        if not sel:
            return await call.answer("Выберите хотя бы один день", show_alert=True)
        await state.set_state(HabitAdd.time)
        return await show(call, "Во сколько напоминать? Формат ЧЧ:ММ, например 07:30")
    if key == "all":
        sel = set(range(7))
    elif key == "wd":
        sel = set(range(5))
    else:
        sel ^= {int(key)}
    await state.update_data(days=sorted(sel))
    await show(call, "В какие дни напоминать?", days_keyboard(sel))


@router.message(HabitAdd.time, F.text)
async def add_time(message: Message, state: FSMContext, db, scheduler: HabitScheduler, tz: str):
    m = TIME_RE.match(message.text.strip())
    if not m:
        return await message.answer("Не понял время. Формат ЧЧ:ММ, например 07:30.")
    time = f"{int(m.group(1)):02d}:{m.group(2)}"
    data = await state.get_data()
    today = datetime.now(ZoneInfo(tz)).date().isoformat()
    hid = await repo.add_habit(db, message.from_user.id, data["name"], ",".join(map(str, data["days"])), time, today)
    await scheduler.sync_habit(hid)
    await state.clear()
    await message.answer(
        f"Привычка добавлена: <b>{html.escape(data['name'])}</b>, {days_label(','.join(map(str, data['days'])))} в {time} ({tz})"
    )
    await render_list(message, db, message.from_user.id)
