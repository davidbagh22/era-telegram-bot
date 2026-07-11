from aiogram.fsm.state import State, StatesGroup


class AuctionBidStates(StatesGroup):
    amount = State()


class AuctionAdminStates(StatesGroup):
    title = State()
    description = State()
    minimum_bid = State()
    bid_step = State()
    ends_at = State()
