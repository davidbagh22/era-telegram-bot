from aiogram.fsm.state import State, StatesGroup


class PartnerAdminStates(StatesGroup):
    name = State()
    description = State()
    source = State()
    edit_source = State()
    initiative_title = State()
    initiative_description = State()
    initiative_source = State()
    initiative_expires_at = State()
    initiative_location = State()
    task_title = State()
    task_description = State()
    task_source = State()
    task_points = State()
    task_deadline = State()
