from aiogram.fsm.state import State, StatesGroup


class OpenTaskStates(StatesGroup):
    title = State()
    description = State()
    deadline = State()
    points = State()
    max_participants = State()
