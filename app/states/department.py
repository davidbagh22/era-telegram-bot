from aiogram.fsm.state import State, StatesGroup


class DepartmentApplicationStates(StatesGroup):
    department = State()
    direction = State()
    motivation = State()
    usefulness = State()
    available_time = State()
