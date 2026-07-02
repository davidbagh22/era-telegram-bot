from aiogram.fsm.state import State, StatesGroup


class QuestionStates(StatesGroup):
    text = State()
    attachment_choice = State()
    attachment = State()
    followup = State()


class AnswerStates(StatesGroup):
    text = State()


class AdminQuestionStates(StatesGroup):
    answer = State()
    forward = State()
