from aiogram.fsm.state import State, StatesGroup


class PartnerAdminStates(StatesGroup):
    name = State()
    description = State()
    source = State()
    edit_value = State()
    initiative_title = State()
    initiative_description = State()
    initiative_source = State()
    task_title = State()
    task_description = State()
    task_points = State()
    task_source = State()
