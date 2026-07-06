from aiogram.fsm.state import State, StatesGroup


class PointTransferStates(StatesGroup):
    recipient = State()
    amount = State()
    confirm = State()
