import html
import logging
from datetime import datetime
from urllib.parse import urlparse

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.socials import SocialLink, SocialProfile
from app.keyboards.common import subscription_keyboard
from app.keyboards.registration import (
    DIRECTION_OPTIONS,
    consent_keyboard,
    directions_keyboard,
    pending_registration_keyboard,
    registration_review_keyboard,
    time_keyboard,
)
from app.keyboards.participant import main_inline_keyboard
from app.repositories.users import create_user_from_registration
from app.services.admin_user_card import send_admin_application_cards
from app.services.audit_service import audit
from app.services.consent_policy import CONSENT_SUMMARY, consent_full_chunks
from app.services.consent_service import CURRENT_POLICY_VERSION
from app.services.notification_service import admin_notification_recipients, safe_send
from app.services.points_service import add_points
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.states.registration import RegistrationStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.validators import clean_text, normalize_email, parse_age

router = Router(name="registration")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
logger = logging.getLogger(__name__)

TIME_VALUES = {
    "1-2": "1–2 часа в неделю",
    "3-5": "3–5 часов в неделю",
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


def application_status_message(status: str) -> str:
    """Return a truthful participant-facing application status.

    Rejection reasons remain internal-only: this presenter exposes the status,
    never the admin comment/reason stored with the application review.
    """
    if status == ApplicationStatus.APPROVED:
        return texts.APPLICATION_APPROVED
    if status == ApplicationStatus.REJECTED:
        return (
            "Статус заявки: не одобрена.\n\n"
            "Доступ участника к закрытым разделам и чатам ЭРА не открыт. "
            "Если вы считаете, что произошла ошибка, напишите команде ЭРА."
        )
    if status == ApplicationStatus.NEEDS_INFO:
        return (
            "Статус заявки: нужно уточнение.\n\n"
            "Команда ЭРА запросила дополнительную информацию. "
            "Проверьте последние сообщения от бота и ответьте на запрос администратора."
        )
    return texts.APPLICATION_PENDING


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


def _parse_skills(value: str) -> list[str]:
    """Turn a natural Telegram answer into a clean, compact skills list."""
    raw_value = (value or "")[:1000]
    if not clean_text(raw_value, 1000):
        return []
    result: list[str] = []
    seen: set[str] = set()
    normalized_separators = raw_value.replace("\r\n", "\n").replace("\r", "\n")
    for raw_item in normalized_separators.replace(";", ",").replace("\n", ",").split(","):
        item = clean_text(raw_item, 120)
        if not item:
            continue
        identity = item.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
        if len(result) >= 20:
            break
    return result


async def _fallback_registration_notice(
    bot: Bot,
    settings: Settings,
    user,
    *,
    auto_approved_admin: bool,
) -> None:
    """Best-effort fallback after the registration is already committed.

    Notification failures must never be able to erase a valid registration.
    Logs intentionally contain only the internal user id, not personal data.
    """
    try:
        recipients = set(await admin_notification_recipients(settings))
    except Exception:
        logger.exception(
            "Failed to resolve registration-notification recipients for user_id=%s",
            user.id,
        )
        recipients = set(settings.admin_ids)

    if not recipients:
        logger.error("No admin recipients configured for registration user_id=%s", user.id)
        return

    status_text = (
        "автоодобрено — системный администратор"
        if auto_approved_admin
        else "ожидает рассмотрения"
    )
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    text = (
        "🆕 Новая регистрация ЭРА\n\n"
        f"{full_name}\n"
        f"Статус: {status_text}.\n\n"
        "Регистрация уже сохранена в базе."
    )
    for admin_id in recipients:
        try:
            await safe_send(bot, admin_id, text)
        except Exception:
            logger.exception(
                "Fallback registration notification failed for user_id=%s",
                user.id,
            )


async def _notify_admins_registration(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    user,
    *,
    auto_approved_admin: bool,
) -> None:
    """Notify admins without letting Telegram affect registration durability."""
    if auto_approved_admin:
        await _fallback_registration_notice(
            bot,
            settings,
            user,
            auto_approved_admin=True,
        )
        return

    try:
        await send_admin_application_cards(bot, settings, session, user)
        return
    except Exception:
        logger.exception(
            "Rich admin registration card failed for user_id=%s; sending fallback",
            user.id,
        )

    try:
        await _fallback_registration_notice(
            bot,
            settings,
            user,
            auto_approved_admin=False,
        )
    except Exception:
        logger.exception(
            "All registration notifications failed for user_id=%s",
            user.id,
        )


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
        await call.message.answer(application_status_message(user.application_status))
        if user.application_status == ApplicationStatus.APPROVED:
            await call.message.answer(
                texts.MAIN_MENU,
                reply_markup=main_inline_keyboard(
                    privileged=user.role in PRIVILEGED_ROLES,
                    admin=user.role == Role.ADMIN,
                    miniapp_url=settings.effective_miniapp_url,
                ),
            )
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
    await state.set_state(RegistrationStates.full_name)
    await call.message.answer(texts.REGISTRATION_INTRO)


def _split_full_name(value: str) -> tuple[str, str] | None:
    parts = [item for item in value.split() if item]
    if len(parts) < 2:
        return None
    return parts[0], " ".join(parts[1:])


@router.message(RegistrationStates.full_name)
async def registration_full_name(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 180)
    parsed = _split_full_name(value or "")
    if parsed is None:
        await message.answer(texts.REG_FULL_NAME_ERROR)
        return
    first_name, last_name = parsed
    await state.update_data(first_name=first_name, last_name=last_name)
    await state.set_state(RegistrationStates.age)
    await message.answer(texts.REG_AGE)


@router.message(RegistrationStates.age)
async def registration_age(message: Message, state: FSMContext) -> None:
    value = parse_age(message.text or "")
    if value is None:
        await message.answer(texts.REG_AGE_ERROR)
        return
    await state.update_data(age=value, birth_date=None)
    await state.set_state(RegistrationStates.country)
    await message.answer(texts.REG_COUNTRY)


@router.message(RegistrationStates.country)
async def registration_country(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer("Напишите название страны текстом.")
        return
    await state.update_data(country=value)
    await state.set_state(RegistrationStates.region)
    await message.answer(texts.REG_REGION)


@router.message(RegistrationStates.region)
async def registration_region(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 120)
    if not value:
        await message.answer("Напишите регион или город текстом.")
        return
    await state.update_data(region=value, city=value)
    await state.set_state(RegistrationStates.email)
    await message.answer(texts.REG_EMAIL)


@router.message(RegistrationStates.email)
async def registration_email(message: Message, state: FSMContext) -> None:
    value = normalize_email(message.text or "")
    if value is None:
        await message.answer(texts.REG_EMAIL_ERROR)
        return
    await state.update_data(email=value)
    await state.set_state(RegistrationStates.education_work)
    await message.answer(texts.REG_EDUCATION)


@router.message(RegistrationStates.education_work)
async def registration_education(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(education_work=value, occupation=value, selected_directions=[])
    await state.set_state(RegistrationStates.directions)
    await message.answer(
        texts.REG_DIRECTION_SIMPLE,
        reply_markup=directions_keyboard("both"),
    )


@router.callback_query(RegistrationStates.directions, F.data.startswith("reg:dir:"))
async def registration_directions(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    selected = set(data.get("selected_directions", []))

    if key == "done":
        if not selected:
            await call.message.answer(texts.REG_DIRECTION_REQUIRED)
            return
        names = [DIRECTION_OPTIONS[item] for item in selected if item != "participate"]
        departments: list[str] = []
        if any(item in selected for item in ("leadership", "culture", "interactive")):
            departments.append("Внутренние связи")
        if any(item in selected for item in ("international", "media", "social")):
            departments.append("Внешние связи")
        await state.update_data(directions=names, departments=departments)
        await state.set_state(RegistrationStates.experience)
        await call.message.answer(texts.REG_EXPERIENCE_SIMPLE)
        return

    if key not in DIRECTION_OPTIONS:
        return
    if key == "participate":
        selected = {"participate"} if "participate" not in selected else set()
    else:
        selected.discard("participate")
        if key in selected:
            selected.remove(key)
        else:
            selected.add(key)
    await state.update_data(selected_directions=list(selected))
    await call.message.edit_reply_markup(
        reply_markup=directions_keyboard("both", selected)
    )


@router.message(RegistrationStates.experience)
async def registration_experience(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1200)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(experience=value, skills=[])
    await state.set_state(RegistrationStates.available_time)
    await message.answer(texts.REG_TIME, reply_markup=time_keyboard())


@router.callback_query(
    RegistrationStates.available_time,
    F.data.startswith("reg:time:"),
)
async def registration_available_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    if key not in TIME_VALUES:
        return
    await state.update_data(available_time=TIME_VALUES[key], desired_path="Участник")
    await state.set_state(RegistrationStates.motivation)
    await call.message.answer(texts.REG_MOTIVATION)


def _registration_review_text(data: dict) -> str:
    directions = ", ".join(data.get("directions") or []) or "Пока просто участвовать"
    return (
        f"{texts.REG_REVIEW_TITLE}\n\n"
        f"Имя: <b>{html.escape(f\"{data.get('first_name', '')} {data.get('last_name', '')}\".strip())}</b>\n"
        f"Возраст: {html.escape(str(data.get('age') or '—'))}\n"
        f"Страна: {html.escape(str(data.get('country') or '—'))}\n"
        f"Регион / город: {html.escape(str(data.get('region') or '—'))}\n"
        f"Email: {html.escape(str(data.get('email') or '—'))}\n"
        f"Учёба / работа: {html.escape(str(data.get('education_work') or '—'))}\n"
        f"Интересы: {html.escape(directions)}\n"
        f"Время: {html.escape(str(data.get('available_time') or '—'))}\n\n"
        f"<b>Опыт / чем полезны</b>\n{html.escape(str(data.get('experience') or '—'))}\n\n"
        f"<b>Почему ЭРА</b>\n{html.escape(str(data.get('motivation') or '—'))}"
    )


@router.message(RegistrationStates.motivation)
async def registration_motivation(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1200)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(
        motivation=value,
        phone=None,
        profile_photo_file_id=None,
        social_url=None,
    )
    data = await state.get_data()
    await state.set_state(RegistrationStates.review)
    await message.answer(
        _registration_review_text(data),
        reply_markup=registration_review_keyboard(),
    )


@router.callback_query(RegistrationStates.review, F.data == "reg:review:restart")
async def registration_review_restart(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await state.set_state(RegistrationStates.full_name)
    await call.message.answer(texts.REGISTRATION_INTRO)


@router.callback_query(RegistrationStates.review, F.data == "reg:review:ok")
async def registration_review_ok(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(consent_policy_version=CURRENT_POLICY_VERSION)
    await state.set_state(RegistrationStates.consent)
    await call.message.answer(CONSENT_SUMMARY, reply_markup=consent_keyboard())


@router.callback_query(RegistrationStates.consent, F.data == "reg:consent:full")
async def full_consent(call: CallbackQuery) -> None:
    await call.answer()
    chunks = consent_full_chunks()
    for index, chunk in enumerate(chunks):
        await call.message.answer(
            chunk,
            reply_markup=consent_keyboard() if index == len(chunks) - 1 else None,
        )


@router.callback_query(RegistrationStates.consent, F.data == "reg:consent:no")
async def no_consent(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer(texts.REG_NO_CONSENT)


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
        await call.message.answer(
            "Для регистрации нужны фото профиля и ссылка на соцсеть. "
            "Пройдите эти шаги заново."
        )
        await state.set_state(RegistrationStates.profile_photo)
        return
    if data.get("consent_policy_version") != CURRENT_POLICY_VERSION:
        # A long-running Telegram FSM can survive a deploy. Never record
        # consent against a new policy version when the participant only
        # saw the previous one: show the current text and require a fresh
        # explicit click instead.
        await state.update_data(consent_policy_version=CURRENT_POLICY_VERSION)
        await call.message.answer(
            "Условия обработки данных обновились. Пожалуйста, ознакомьтесь "
            "с актуальной версией и подтвердите её ещё раз.\n\n"
            f"{CONSENT_SUMMARY}",
            reply_markup=consent_keyboard(),
        )
        return
    user, created = await create_user_from_registration(
        session,
        telegram_id=call.from_user.id,
        username=call.from_user.username,
        data=data,
    )
    if created:
        now = datetime.now().astimezone()
        session.add(
            SocialProfile(
                user_id=user.id,
                photo_file_id=data.get("profile_photo_file_id"),
                contact_email=user.email,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SocialLink(
                user_id=user.id,
                url=data["social_url"],
                platform=_platform_from_url(data["social_url"]),
                created_at=now,
                updated_at=now,
            )
        )

    auto_approved_admin = call.from_user.id in settings.admin_ids
    if auto_approved_admin:
        # Preserve bootstrap/admin access semantics, but do not silently
        # hide the registration event: after commit admins receive an
        # explicit "auto-approved" registration notice.
        user.role = Role.ADMIN
        user.application_status = ApplicationStatus.APPROVED
        if created:
            await add_points(
                session,
                user_id=user.id,
                points=5,
                reason="Регистрация в боте",
                approved_by=user.id,
                source_type="registration",
                source_id=user.id,
                idempotency_key=f"registration:{user.id}",
            )
    if created:
        await audit(
            session,
            actor_id=user.id,
            action="user.registered",
            entity_type="user",
            entity_id=user.id,
            new_value={"telegram_id": user.telegram_id},
        )

    # Critical durability boundary: the registration, consent, profile,
    # social link, role/status and audit event are committed BEFORE any
    # Telegram notification or success screen is attempted. The outer bot
    # middleware may later roll back a new transaction if Telegram fails,
    # but it can no longer erase this already-committed registration.
    await session.flush()
    await session.commit()
    await state.clear()

    if user.application_status == ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_APPROVED)
        await call.message.answer(
            texts.MAIN_MENU,
            reply_markup=main_inline_keyboard(
                privileged=user.role in PRIVILEGED_ROLES,
                admin=user.role == Role.ADMIN,
                miniapp_url=settings.effective_miniapp_url,
            ),
        )
    else:
        await call.message.answer(
            texts.REG_DONE,
            reply_markup=pending_registration_keyboard(settings.era_channel_url),
        )

    if created:
        await _notify_admins_registration(
            bot,
            settings,
            session,
            user,
            auto_approved_admin=auto_approved_admin,
        )


@router.callback_query(F.data == "registration:status")
async def registration_status(call: CallbackQuery, user, settings: Settings) -> None:
    await call.answer()
    if user is None:
        await call.message.answer(texts.WELCOME)
        return
    if user.application_status == ApplicationStatus.APPROVED:
        await call.message.answer(
            application_status_message(user.application_status),
            reply_markup=main_inline_keyboard(
                privileged=user.role in PRIVILEGED_ROLES,
                admin=user.role == Role.ADMIN,
                miniapp_url=settings.effective_miniapp_url,
            ),
        )
        return
    await call.message.answer(
        application_status_message(user.application_status),
        reply_markup=(
            pending_registration_keyboard(settings.era_channel_url)
            if user.application_status in {ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO}
            else None
        ),
    )
