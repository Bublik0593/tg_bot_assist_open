from aiogram.fsm.state import State, StatesGroup


class HabitAdd(StatesGroup):
    name = State()
    days = State()
    time = State()


class GoalAdd(StatesGroup):
    title = State()
    description = State()


class GoalEdit(StatesGroup):
    title = State()


class TzManual(StatesGroup):
    name = State()


class BookJump(StatesGroup):
    page = State()
