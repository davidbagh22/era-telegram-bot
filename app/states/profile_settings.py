from aiogram.fsm.state import State, StatesGroup


class ProfileSettingsStates(StatesGroup):
    text_value = State()
    birth_date = State()
    phone = State()
    email = State()
    photo = State()
    social_url = State()
    contact_email = State()
