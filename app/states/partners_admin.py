from aiogram.fsm.state import State, StatesGroup


class PartnerAdminStates(StatesGroup):
    name = State()
    description = State()
    source = State()
    edit_source = State()
