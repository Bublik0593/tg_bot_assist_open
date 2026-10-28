from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


async def show(target: Message | CallbackQuery, text: str, markup=None, **kwargs) -> None:
    """Для callback редактирует исходное сообщение, для сообщения отправляет новое."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=markup, **kwargs)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup, **kwargs)


def short(s: str, n: int = 40) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"
