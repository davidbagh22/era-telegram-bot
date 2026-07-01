from aiogram.fsm.state import State, StatesGroup


class EventStates(StatesGroup):
    idea = State()
    title = State()
    description = State()
    event_date = State()
    event_time = State()
    location = State()
    department = State()
    direction = State()
    format = State()
    participant_limit = State()
    points = State()
    selfie_required = State()
    poster = State()


class FeedbackStates(StatesGroup):
    rating = State()
    liked = State()
    improve = State()
    wants_again = State()


class SelfieStates(StatesGroup):
    photo = State()


class EventActivityStates(StatesGroup):
    submission = State()
