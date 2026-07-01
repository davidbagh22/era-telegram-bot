from aiogram.fsm.state import State, StatesGroup


class PortfolioUploadStates(StatesGroup):
    title = State()
    description = State()
    file = State()


class AuctionBidStates(StatesGroup):
    amount = State()


class TaskSubmissionStates(StatesGroup):
    result = State()
