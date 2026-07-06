from aiogram.fsm.state import State, StatesGroup


class ProfileSettingsStates(StatesGroup):
    photo = State()
    social_url = State()
    contact_email = State()
