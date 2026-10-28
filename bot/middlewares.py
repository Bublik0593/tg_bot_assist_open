from aiogram import BaseMiddleware
from aiogram.types import Message

from .db import repo
from .keyboards import MENU_TEXTS


class UserMiddleware(BaseMiddleware):
    """Создаёт пользователя при первом обращении, кладёт его часовой пояс в data['tz'].

    Нажатие кнопки меню или команда сбрасывают незавершённый диалог (FSM).
    """

    def __init__(self, db, default_tz: str):
        self.db = db
        self.default_tz = default_tz

    async def __call__(self, handler, event, data):
        user = event.from_user
        if user is None:
            return await handler(event, data)
        data["tz"] = await repo.ensure_user(self.db, user.id, self.default_tz)
        if isinstance(event, Message) and event.text and (event.text in MENU_TEXTS or event.text.startswith("/")):
            state = data.get("state")
            if state:
                await state.clear()
        return await handler(event, data)
