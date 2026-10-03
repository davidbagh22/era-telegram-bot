from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    # Current streamlined registration flow.
    full_name = State()
    age = State()
    country = State()
    region = State()
    email = State()
    education_work = State()
    directions = State()
    experience = State()
    available_time = State()
    motivation = State()
    review = State()
    consent = State()

    # Legacy states kept for compatibility with old in-flight FSM snapshots.
    first_name = State()
    last_name = State()
    birth_date = State()
    phone = State()
    city = State()
    occupation = State()
    skills = State()
    department = State()
    desired_path = State()
    profile_photo = State()
    social_url = State()
    referral_code = State()
