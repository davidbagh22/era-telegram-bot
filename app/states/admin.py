from aiogram.fsm.state import State, StatesGroup


class AdminReviewStates(StatesGroup):
    comment = State()


class AdminAnswerStates(StatesGroup):
    answer = State()


class AdminBroadcastStates(StatesGroup):
    audience = State()
    filter_value = State()
    text = State()
    confirm = State()
