import asyncio
import io
import os

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import repo
from ..keyboards import BTN_BOOKS
from ..services.pagination import decode_text, normalize, paginate
from ..states import BookJump
from ..utils import short, show

router = Router()


async def render_list(target, db, user_id: int):
    books = await repo.list_books(db, user_id)
    if not books:
        return await show(target, "📚 <b>Книги</b>\nПока нет ни одной. Отправьте мне файл в формате <b>.txt</b>.")
    rows = [
        [B(text=f"📖 {short(b['title'], 32)} · {b['current_page']}/{b['total_pages']}", callback_data=f"bk:o:{b['id']}")]
        for b in books
    ]
    await show(target, "📚 <b>Книги</b>\nВыберите книгу или отправьте новый .txt файл.", InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text == BTN_BOOKS)
async def menu(message: Message, db):
    await render_list(message, db, message.from_user.id)


@router.callback_query(F.data == "bk:list")
async def back(call: CallbackQuery, db):
    await render_list(call, db, call.from_user.id)


# --- загрузка ---
@router.message(F.document)
async def upload(message: Message, bot: Bot, db, cfg: Config):
    doc = message.document
    name = doc.file_name or "book.txt"
    if not name.lower().endswith(".txt"):
        return await message.answer("Поддерживается только формат .txt")
    if doc.file_size and doc.file_size > cfg.max_book_bytes:
        return await message.answer(f"Файл слишком большой (максимум {cfg.max_book_bytes // 1024 // 1024} МБ).")
    wait = await message.answer("Загружаю и разбиваю на страницы…")
    buf = io.BytesIO()
    await bot.download(doc, destination=buf)
    pages = await asyncio.to_thread(lambda: paginate(decode_text(buf.getvalue()), cfg.page_size))
    if not pages:
        return await wait.edit_text("Файл пустой, добавлять нечего.")
    title = os.path.splitext(name)[0][:100]
    book_id = await repo.add_book(db, message.from_user.id, title, name, pages)
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="📖 Читать", callback_data=f"bk:o:{book_id}")]])
    await wait.edit_text(f"Книга «{title}» добавлена: {len(pages)} стр.", reply_markup=kb)


# --- чтение ---
def reader_keyboard(book_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(B(text="◀", callback_data=f"bk:p:{book_id}:{page - 1}"))
    nav.append(B(text=f"{page}/{total}", callback_data=f"bk:j:{book_id}"))
    if page < total:
        nav.append(B(text="▶", callback_data=f"bk:p:{book_id}:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [B(text="📚 К списку", callback_data="bk:list"), B(text="🗑 Удалить", callback_data=f"bk:d:{book_id}")],
    ])


async def show_page(target, db, user_id: int, book_id: int, page: int):
    book = await repo.get_book(db, user_id, book_id)
    if not book:
        return await render_list(target, db, user_id)
    page = max(1, min(page, book["total_pages"]))
    text = await repo.get_page(db, user_id, book_id, page)
    if text is None:
        return await render_list(target, db, user_id)
    await repo.save_progress(db, user_id, book_id, page)  # прогресс пишется при каждом листании
    header = f"📖 {book['title']} — стр. {page}/{book['total_pages']}\n\n"
    await show(target, header + text, reader_keyboard(book_id, page, book["total_pages"]), parse_mode=None)


@router.callback_query(F.data.regexp(r"^bk:o:\d+$"))
async def open_book(call: CallbackQuery, db):
    book = await repo.get_book(db, call.from_user.id, int(call.data.split(":")[2]))
    if not book:
        return await render_list(call, db, call.from_user.id)
    await show_page(call, db, call.from_user.id, book["id"], book["current_page"])


@router.callback_query(F.data.regexp(r"^bk:p:\d+:\d+$"))
async def turn(call: CallbackQuery, db):
    _, _, bid, page = call.data.split(":")
    await show_page(call, db, call.from_user.id, int(bid), int(page))


@router.callback_query(F.data.regexp(r"^bk:j:\d+$"))
async def jump_ask(call: CallbackQuery, state: FSMContext, db):
    book_id = int(call.data.split(":")[2])
    book = await repo.get_book(db, call.from_user.id, book_id)
    if not book:
        return await render_list(call, db, call.from_user.id)
    await state.set_state(BookJump.page)
    await state.update_data(book_id=book_id, total=book["total_pages"])
    await call.message.answer(f"Номер страницы (1–{book['total_pages']})? /cancel — отмена")
    await call.answer()


@router.message(BookJump.page, F.text)
async def jump_do(message: Message, state: FSMContext, db):
    data = await state.get_data()
    if not message.text.strip().isdigit() or not 1 <= int(message.text) <= data["total"]:
        return await message.answer(f"Введите число от 1 до {data['total']}.")
    await state.clear()
    await show_page(message, db, message.from_user.id, data["book_id"], int(message.text))


# --- удаление ---
@router.callback_query(F.data.regexp(r"^bk:d:\d+$"))
async def delete_ask(call: CallbackQuery):
    bid = call.data.split(":")[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        B(text="Да, удалить", callback_data=f"bk:dy:{bid}"), B(text="Отмена", callback_data=f"bk:o:{bid}"),
    ]])
    await show(call, "Удалить книгу и прогресс чтения?", kb)


@router.callback_query(F.data.regexp(r"^bk:dy:\d+$"))
async def delete_yes(call: CallbackQuery, db):
    await repo.delete_book(db, call.from_user.id, int(call.data.split(":")[2]))
    await render_list(call, db, call.from_user.id)
