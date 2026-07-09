from datetime import datetime
from urllib.parse import urlparse

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.socials import SocialLink, SocialProfile
from app.keyboards.admin import application_actions
from app.keyboards.common import subscription_keyboard
from app.keyboards.registration import (
    DEPARTMENT_OPTIONS,
    DIRECTION_OPTIONS,
    consent_keyboard,
    department_keyboard,
    desired_path_keyboard,
    directions_keyboard,
    pending_registration_keyboard,
    time_keyboard,
)
from app.keyboards.participant import main_menu
from app.repositories.users import create_user_from_registration
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.services.points_service import add_points
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.states.registration import RegistrationStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.validators import clean_text, normalize_email, normalize_phone, parse_age

router = Router(name="registration")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

PATHS = (
    "Участник",
    "Активист",
    "Лидер",
    "Руководитель",
    "Совет",
)

TIME_VALUES = {
    "1-2": "1–2 часа в неделю",
    "3-5": "3–5 часов в неделю",
    "daily1": "1 час в день",
    "daily_more": "Несколько часов в день",
    "active": "Готов активно включаться",
}

PLATFORMS = {
    "t.me": "Telegram",
    "telegram.me": "Telegram",
    "instagram.com": "Instagram",
    "vk.com": "VK",
    "linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
}


def _platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, platform in PLATFORMS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return "Сайт"


def _normalize_url(value: str) -> str | None:
    value = " ".join((value or "").split()).strip()
    if not value or len(value) > 500:
        return None
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or "." not in parsed.netloc:
        return None
    return value


@router.callback_query(F.data == "registration:start")
async def registration_start(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    user,
) -> None:
    await call.answer()
    if user is not None:
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    try:
        subscribed = await is_channel_member(bot, call.from_user.id, settings)
    except SubscriptionCheckError:
        await call.message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if not subscribed:
        await call.message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    await state.clear()
    await state.set_state(RegistrationStates.first_name)
    await call.message.answer(texts.REGISTRATION_INTRO)


@router.message(RegistrationStates.first_name)
async def first_name(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(first_name=value)
    await state.set_state(RegistrationStates.last_name)
    await message.answer(texts.REG_LAST_NAME)


@router.message(RegistrationStates.last_name)
async def last_name(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(last_name=value)
    await state.set_state(RegistrationStates.age)
    await message.answer(texts.REG_AGE)


@router.message(RegistrationStates.age)
async def age(message: Message, state: FSMContext) -> None:
    value = parse_age(message.text or "")
    if value is None:
        await message.answer(texts.REG_AGE_ERROR)
        return
    await state.update_data(age=value)
    await state.set_state(RegistrationStates.phone)
    await message.answer(texts.REG_PHONE)


@router.message(RegistrationStates.phone)
async def phone(message: Message, state: FSMContext) -> None:
    raw = message.contact.phone_number if message.contact else (message.text or "")
    value = normalize_phone(raw)
    if value is None:
        await message.answer(texts.REG_PHONE_ERROR)
        return
    await state.update_data(phone=value)
    await state.set_state(RegistrationStates.email)
    await message.answer(texts.REG_EMAIL)


@router.message(RegistrationStates.email)
async def email(message: Message, state: FSMContext) -> None:
    value = normalize_email(message.text or "")
    if value is None:
        await message.answer(texts.REG_EMAIL_ERROR)
        return
    await state.update_data(email=value)
    await state.set_state(RegistrationStates.city)
    await message.answer(texts.REG_CITY)


async def _save_text_and_advance(
    message: Message,
    state: FSMContext,
    key: str,
    next_state,
    prompt: str,
    max_length: int = 1000,
) -> None:
    value = clean_text(message.text or "", max_length)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(**{key: value})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(RegistrationStates.city)
async def city(message: Message, state: FSMContext) -> None:
    await _save_text_and_advance(message, state, "city", RegistrationStates.education_work, texts.REG_EDUCATION, 100)


@router.message(RegistrationStates.education_work)
async def education(message: Message, state: FSMContext) -> None:
    await _save_text_and_advance(message, state, "education_work", RegistrationStates.occupation, texts.REG_OCCUPATION, 255)


@router.message(RegistrationStates.occupation)
async def occupation(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(occupation=value)
    await state.set_state(RegistrationStates.department)
    await message.answer(texts.REG_DEPARTMENT, reply_markup=department_keyboard())


@router.callback_query(RegistrationStates.department, F.data.startswith("reg:dept:"))
async def department(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    if key not in DEPARTMENT_OPTIONS:
        return
    departments = {
        "internal": ["Внутренние связи"],
        "external": ["Внешние связи"],
        "both": ["Внутренние связи", "Внешние связи"],
        "unsure": [],
    }[key]
    prompt = {
        "internal": texts.REG_INTERNAL,
        "external": texts.REG_EXTERNAL,
        "both": texts.REG_BOTH,
        "unsure": texts.REG_UNSURE,
    }[key]
    await state.update_data(department_scope=key, departments=departments, selected_directions=[])
    await state.set_state(RegistrationStates.directions)
    await call.message.answer(f"{prompt}\n\n{texts.REG_DIRECTION_HINT}", reply_markup=directions_keyboard(key))


@router.callback_query(RegistrationStates.directions, F.data.startswith("reg:dir:"))
async def directions(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    selected = set(data.get("selected_directions", []))
    if key == "done":
        if not selected:
            await call.message.answer(texts.REG_DIRECTION_REQUIRED)
            return
        names = [DIRECTION_OPTIONS[item] for item in selected if item != "participate"]
        departments = list(data.get("departments", []))
        if not departments:
            if any(item in selected for item in ("leadership", "culture", "interactive")):
                departments.append("Внутренние связи")
            if any(item in selected for item in ("international", "media", "social")):
                departments.append("Внешние связи")
        await state.update_data(directions=names, departments=departments)
        await state.set_state(RegistrationStates.available_time)
        await call.message.answer(texts.REG_TIME, reply_markup=time_keyboard())
        return
    if key not in DIRECTION_OPTIONS:
        return
    if key in selected:
        selected.remove(key)
    else:
        selected.add(key)
    await state.update_data(selected_directions=list(selected))
    await call.message.edit_reply_markup(reply_markup=directions_keyboard(data.get("department_scope", "both"), selected))


@router.callback_query(RegistrationStates.available_time, F.data.startswith("reg:time:"))
async def available_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    if key not in TIME_VALUES:
        return
    await state.update_data(available_time=TIME_VALUES[key], skills=[])
    await state.set_state(RegistrationStates.desired_path)
    await call.message.answer(texts.REG_DESIRED_PATH, reply_markup=desired_path_keyboard())


@router.callback_query(RegistrationStates.desired_path, F.data.startswith("reg:path:"))
async def desired_path(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    try:
        value = PATHS[int(call.data.rsplit(":", 1)[-1])]
    except (ValueError, IndexError):
        return
    await state.update_data(desired_path=value)
    await state.set_state(RegistrationStates.motivation)
    await call.message.answer(texts.REG_MOTIVATION)


@router.message(RegistrationStates.motivation)
async def motivation(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1500)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(motivation=value)
    await state.set_state(RegistrationStates.profile_photo)
    await message.answer("Отправьте фото для профиля.\n\nФото обязательно для регистрации в ЭРА.")


@router.message(RegistrationStates.profile_photo, F.photo)
async def registration_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(profile_photo_file_id=message.photo[-1].file_id)
    await state.set_state(RegistrationStates.social_url)
    await message.answer("Отправьте ссылку на соцсеть: Telegram, Instagram, LinkedIn или сайт.\n\nСсылка обязательна для регистрации в ЭРА.")


@router.message(RegistrationStates.profile_photo)
async def registration_photo_required(message: Message, state: FSMContext) -> None:
    await message.answer("Фото обязательно. Отправьте реальное фото одним сообщением, чтобы продолжить регистрацию.")


@router.message(RegistrationStates.social_url)
async def registration_social(message: Message, state: FSMContext) -> None:
    url = _normalize_url(message.text or "")
    if url is None:
        await message.answer("Ссылка на соцсеть обязательна. Пример: t.me/username или instagram.com/name.")
        return
    await state.update_data(social_url=url)
    await state.set_state(RegistrationStates.consent)
    await message.answer(texts.REG_CONSENT, reply_markup=consent_keyboard())


@router.callback_query(RegistrationStates.consent, F.data == "reg:consent:no")
async def no_consent(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer(texts.REG_NO_CONSENT)


def _application_notification(user) -> str:
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    departments = ", ".join(item.department.name for item in user.departments) or "пока не выбраны"
    directions = ", ".join(item.direction.name for item in user.directions) or "пока не выбраны"
    return (
        "📝 Новая заявка в ЭРА\n\n"
        f"👤 {user.first_name} {user.last_name or ''}\n"
        f"🎂 Возраст: {user.age or 'не указан'}\n"
        f"📍 Город: {user.city or 'не указан'}\n"
        f"📱 Телефон: {user.phone or 'не указан'}\n"
        f"🎓 Учёба / работа: {user.education_work or 'не указано'}\n"
        f"💼 Занятие: {user.occupation or 'не указано'}\n"
        f"📧 Email: {user.email or 'не указан'}\n"
        f"💬 Telegram: {telegram}\n\n"
        f"🧭 Желаемый путь: {user.desired_path or 'не указан'}\n"
        f"⏳ Доступное время: {user.available_time or 'не указано'}\n"
        f"🏛 Департаменты: {departments}\n"
        f"✨ Направления: {directions}\n\n"
        f"Мотивация\n{user.motivation or 'не указана'}\n\n"
        "Выберите действие ниже."
    )


@router.callback_query(RegistrationStates.consent, F.data == "reg:consent:yes")
async def finish_registration(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    data = await state.get_data()
    if not data.get("profile_photo_file_id") or not data.get("social_url"):
        await call.message.answer("Для регистрации нужны фото профиля и ссылка на соцсеть. Пройдите эти шаги заново.")
        await state.set_state(RegistrationStates.profile_photo)
        return
    user, created = await create_user_from_registration(session, telegram_id=call.from_user.id, username=call.from_user.username, data=data)
    if created:
        now = datetime.now().astimezone()
        session.add(SocialProfile(user_id=user.id, photo_file_id=data.get("profile_photo_file_id"), contact_email=user.email, created_at=now, updated_at=now))
        session.add(SocialLink(user_id=user.id, url=data["social_url"], platform=_platform_from_url(data["social_url"]), created_at=now, updated_at=now))
    if call.from_user.id in settings.admin_ids:
        user.role = Role.ADMIN
        user.application_status = ApplicationStatus.APPROVED
        if created:
            await add_points(session, user_id=user.id, points=5, reason="Регистрация в боте", approved_by=user.id)
    if created:
        await audit(session, actor_id=user.id, action="user.registered", entity_type="user", entity_id=user.id, new_value={"telegram_id": user.telegram_id})
    await session.flush()
    await state.clear()
    if user.application_status == ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_APPROVED)
        await call.message.answer(texts.MAIN_MENU, reply_markup=main_menu(settings.era_channel_url, privileged=user.role in PRIVILEGED_ROLES, admin=user.role == Role.ADMIN))
    else:
        await call.message.answer(texts.REG_DONE, reply_markup=pending_registration_keyboard(settings.era_channel_url))
        await notify_admins(bot, settings, _application_notification(user), reply_markup=application_actions(user.id))


@router.callback_query(F.data == "registration:status")
async def registration_status(call: CallbackQuery, user, settings: Settings) -> None:
    await call.answer()
    if user is None:
        await call.message.answer(texts.WELCOME)
        return
    if user.application_status == ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_APPROVED, reply_markup=main_menu(settings.era_channel_url, privileged=user.role in PRIVILEGED_ROLES, admin=user.role == Role.ADMIN))
        return
    await call.message.answer(texts.APPLICATION_PENDING, reply_markup=pending_registration_keyboard(settings.era_channel_url))
