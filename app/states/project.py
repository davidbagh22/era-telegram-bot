from aiogram.fsm.state import State, StatesGroup


class ProjectStates(StatesGroup):
    idea = State()
    department = State()
    direction = State()
    target_audience = State()
    relevance = State()
    goal = State()
    format = State()
    program = State()
    resources = State()
    team = State()
    expected_result = State()
    needs_from_era = State()


class ProjectRevisionStates(StatesGroup):
    instruction = State()
