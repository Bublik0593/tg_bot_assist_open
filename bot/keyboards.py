from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BTN_HABITS = "✅ Привычки"
BTN_GOALS = "🎯 Цели"
BTN_BOOKS = "📚 Книги"
BTN_SETTINGS = "⚙️ Настройки"
MENU_TEXTS = {BTN_HABITS, BTN_GOALS, BTN_BOOKS, BTN_SETTINGS}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_HABITS), KeyboardButton(text=BTN_GOALS)],
            [KeyboardButton(text=BTN_BOOKS), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
    )
