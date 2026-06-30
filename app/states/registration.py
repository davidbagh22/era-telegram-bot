from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    first_name = State()
    last_name = State()
    age = State()
    phone = State()
    city = State()
    education_work = State()
    occupation = State()
    department = State()
    directions = State()
    available_time = State()
    skills = State()
    experience = State()
    desired_path = State()
    motivation = State()
    consent = State()
