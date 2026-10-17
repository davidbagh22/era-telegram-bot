from aiogram.fsm.state import State, StatesGroup


class QuestionStates(StatesGroup):
    category = State()
    followup = State()
    text = State()
    attachment_choice = State()
    attachment = State()


class AnswerStates(StatesGroup):
    text = State()
