from aiogram.fsm.state import State, StatesGroup


class TaskStates(StatesGroup):
    assignee = State()
    title = State()
    description = State()
    deadline = State()
    points = State()


class ReportStates(StatesGroup):
    report_type = State()
    content = State()


class ProposalStates(StatesGroup):
    proposal_type = State()
    target = State()
    value = State()
    reason = State()


class BroadcastStates(StatesGroup):
    audience = State()
    text = State()
    confirm = State()
