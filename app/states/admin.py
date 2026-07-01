from aiogram.fsm.state import State, StatesGroup


class AdminReviewStates(StatesGroup):
    comment = State()


class AdminAnswerStates(StatesGroup):
    answer = State()


class AdminBroadcastStates(StatesGroup):
    audience = State()
    filter_value = State()
    text = State()
    confirm = State()


class AdminPeopleStates(StatesGroup):
    search = State()


class AdminGrowthStates(StatesGroup):
    person = State()
    points = State()
    reason = State()
    greeting = State()


class AdminOfficeStates(StatesGroup):
    person = State()
    title = State()
    description = State()


class AdminRewardStates(StatesGroup):
    name = State()
    description = State()
    cost = State()
    quantity = State()


class AdminAuctionStates(StatesGroup):
    audience = State()
    title = State()
    description = State()
    minimum = State()
    step = State()
    deadline = State()
    winners = State()


class AdminEventActivityStates(StatesGroup):
    title = State()
    description = State()
    submission_type = State()
    points = State()
    deadline = State()


class AdminTaskStates(StatesGroup):
    mode = State()
    audience = State()
    person = State()
    title = State()
    description = State()
    deadline = State()
    points = State()
    max_participants = State()
    chat_url = State()


class AdminSettingsStates(StatesGroup):
    chat_bind = State()
    link_edit = State()


class AdminMaintenanceStates(StatesGroup):
    confirm = State()


class AdminCertificateStates(StatesGroup):
    person = State()
    title = State()
    file = State()


class AdminPermissionStates(StatesGroup):
    person = State()
