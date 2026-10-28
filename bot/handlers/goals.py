import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from ..db import repo
from ..keyboards import BTN_GOALS
from ..states import GoalAdd, GoalEdit
from ..utils import short, show

router = Router()
TITLES = {"open": "Активные", "done": "Выполненные", "all": "Все"}
MAX_SHOWN = 50


async def render_list(target, db, user_id: int, flt: str = "open"):
    goals = await repo.list_goals(db, user_id, flt)
    rows = [
        [B(text=f"{'✅' if g['is_done'] else '⬜'} {short(g['title'])}", callback_data=f"g:v:{g['id']}:{flt}")]
        for g in goals[:MAX_SHOWN]
    ]
    rows.append([B(text=("• " if k == flt else "") + v, callback_data=f"g:l:{k}") for k, v in TITLES.items()])
    rows.append([B(text="➕ Добавить цель", callback_data="g:a")])
    text = f"🎯 <b>Цели — {TITLES[flt]}</b> ({len(goals)})"
    if not goals:
        text += "\nПока пусто."
    elif len(goals) > MAX_SHOWN:
        text += f"\nПоказаны первые {MAX_SHOWN}."
    await show(target, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text == BTN_GOALS)
async def menu(message: Message, db):
    await render_list(message, db, message.from_user.id)


@router.callback_query(F.data.regexp(r"^g:l:(open|done|all)$"))
async def list_cb(call: CallbackQuery, db):
    await render_list(call, db, call.from_user.id, call.data.split(":")[2])


async def render_goal(call: CallbackQuery, db, goal_id: int, flt: str):
    g = await repo.get_goal(db, call.from_user.id, goal_id)
    if not g:
        return await render_list(call, db, call.from_user.id, flt)
    status = f"✅ выполнена {g['done_at']} (UTC)" if g["is_done"] else "⬜ не выполнена"
    text = f"<b>{html.escape(g['title'])}</b>\n{status}"
    if g["description"]:
        text += f"\n\n{html.escape(g['description'])}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="↩️ Вернуть в активные" if g["is_done"] else "✅ Выполнено", callback_data=f"g:t:{goal_id}:{flt}")],
        [B(text="✏️ Переименовать", callback_data=f"g:e:{goal_id}"), B(text="🗑 Удалить", callback_data=f"g:d:{goal_id}:{flt}")],
        [B(text="⬅️ К списку", callback_data=f"g:l:{flt}")],
    ])
    await show(call, text, kb)


@router.callback_query(F.data.regexp(r"^g:v:\d+:(open|done|all)$"))
async def view(call: CallbackQuery, db):
    _, _, gid, flt = call.data.split(":")
    await render_goal(call, db, int(gid), flt)


@router.callback_query(F.data.regexp(r"^g:t:\d+:(open|done|all)$"))
async def toggle(call: CallbackQuery, db):
    _, _, gid, flt = call.data.split(":")
    await repo.toggle_goal(db, call.from_user.id, int(gid))
    await render_goal(call, db, int(gid), flt)


@router.callback_query(F.data.regexp(r"^g:d:\d+:(open|done|all)$"))
async def delete_ask(call: CallbackQuery):
    _, _, gid, flt = call.data.split(":")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        B(text="Да, удалить", callback_data=f"g:dy:{gid}:{flt}"), B(text="Отмена", callback_data=f"g:v:{gid}:{flt}"),
    ]])
    await show(call, "Удалить цель?", kb)


@router.callback_query(F.data.regexp(r"^g:dy:\d+:(open|done|all)$"))
async def delete_yes(call: CallbackQuery, db):
    _, _, gid, flt = call.data.split(":")
    await repo.delete_goal(db, call.from_user.id, int(gid))
    await render_list(call, db, call.from_user.id, flt)


# --- добавление ---
@router.callback_query(F.data == "g:a")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(GoalAdd.title)
    await show(call, "Название цели? (/cancel — отмена)")


@router.message(GoalAdd.title, F.text)
async def add_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title or len(title) > 200:
        return await message.answer("Название должно быть от 1 до 200 символов.")
    await state.update_data(title=title)
    await state.set_state(GoalAdd.description)
    await message.answer("Описание? Отправьте «-», чтобы пропустить.")


@router.message(GoalAdd.description, F.text)
async def add_desc(message: Message, state: FSMContext, db):
    data = await state.get_data()
    desc = "" if message.text.strip() == "-" else message.text.strip()[:2000]
    await repo.add_goal(db, message.from_user.id, data["title"], desc)
    await state.clear()
    await message.answer("Цель добавлена ✅")
    await render_list(message, db, message.from_user.id)


# --- переименование ---
@router.callback_query(F.data.regexp(r"^g:e:\d+$"))
async def edit_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(GoalEdit.title)
    await state.update_data(goal_id=int(call.data.split(":")[2]))
    await show(call, "Новое название? (/cancel — отмена)")


@router.message(GoalEdit.title, F.text)
async def edit_title(message: Message, state: FSMContext, db):
    title = message.text.strip()
    if not title or len(title) > 200:
        return await message.answer("Название должно быть от 1 до 200 символов.")
    gid = (await state.get_data())["goal_id"]
    await repo.rename_goal(db, message.from_user.id, gid, title)
    await state.clear()
    await message.answer("Переименовано ✅")
    await render_list(message, db, message.from_user.id)
