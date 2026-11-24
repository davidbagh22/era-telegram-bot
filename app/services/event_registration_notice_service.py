"""Transaction-coupled delivery of event registration and waitlist notices."""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import StrEnum

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.database.system_models import NotificationDelivery
from app.services.event_registration_service import registration_stats
from app.services.notification_service import _DELIVERY_LEASE, _delivery_failure, _payload_hash
from app.utils import texts
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import miniapp_event_url

logger = logging.getLogger(__name__)
_NOTICE_TYPE = "event_registration_notice"
_KEY_PREFIX = "event-registration"
_UNAVAILABLE_EVENTS = {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, EventStatus.CANCELLED}


class RegistrationNoticeKind(StrEnum):
    MINI_APP = "miniapp"
    TELEGRAM = "telegram"
    PROMOTION = "promotion"


def _revision(registration: EventRegistration) -> str:
    stamp = registration.updated_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat(timespec="microseconds")


async def enqueue_registration_notice(
    session: AsyncSession, registration: EventRegistration, chat_id: int, kind: RegistrationNoticeKind
) -> str:
    """Store an intent in the same transaction and under the same lock as the state change."""
    key = f"{_KEY_PREFIX}:{registration.id}:{kind}:{registration.status}:{_revision(registration)}"
    existing = await session.scalar(
        select(NotificationDelivery.id).where(NotificationDelivery.delivery_key == key)
    )
    if existing is None:
        session.add(
            NotificationDelivery(
                delivery_key=key, chat_id=chat_id, notification_type=_NOTICE_TYPE,
                status="queued", attempt_count=0, payload_hash=_payload_hash(key),
            )
        )
    return key


def _notice_identity(key: str) -> tuple[int, RegistrationNoticeKind, str, str] | None:
    try:
        prefix, raw_id, raw_kind, status, revision = key.split(":", 4)
        kind = RegistrationNoticeKind(raw_kind)
        registration_id = int(raw_id)
    except ValueError:
        return None
    if prefix != _KEY_PREFIX or not 0 < registration_id <= 2_147_483_647:
        return None
    if status not in {RegistrationStatus.REGISTERED, RegistrationStatus.WAITLIST}:
        return None
    if kind == RegistrationNoticeKind.PROMOTION and status != RegistrationStatus.REGISTERED:
        return None
    return registration_id, kind, status, revision


def _event_keyboard(
    settings: Settings | None, event: Event, experience: EventExperience | None
) -> InlineKeyboardMarkup | None:
    url = miniapp_event_url(settings.effective_miniapp_url, event.id) if settings is not None else None
    rows: list[list[InlineKeyboardButton]] = []
    if url:
        rows.append([InlineKeyboardButton(text="Открыть мероприятие", web_app=WebAppInfo(url=url))])
    if experience and experience.chat_url:
        rows.append([InlineKeyboardButton(text="Открыть чат", url=experience.chat_url)])
    if url:
        rows.append([InlineKeyboardButton(text="Отказаться от участия", web_app=WebAppInfo(url=url))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _message(
    session: AsyncSession, settings: Settings | None, kind: RegistrationNoticeKind,
    event: Event, experience: EventExperience | None, status: str,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if kind == RegistrationNoticeKind.TELEGRAM:
        if status == RegistrationStatus.WAITLIST:
            return f"Вы в листе ожидания на «{event.title}». Сообщим, если для вас освободится место.", None
        stats = await registration_stats(session, event)
        text = texts.event_registered(event) + f"\n\nЗарегистрировано: {stats['registered']}"
        if event.participant_limit is not None:
            text += f"\nСвободных мест: {stats['free']}"
        return text, None

    markup = _event_keyboard(settings, event, experience)
    if kind == RegistrationNoticeKind.PROMOTION:
        return (
            "🔥 Для вас освободилось место\n\n"
            f"Вы теперь зарегистрированы на «{event.title}».\n\n"
            f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n"
            f"📍 {event.location}",
            markup,
        )

    details = f"{event.title}\n\n📅 {event.event_date:%d.%m.%Y}\n🕐 {event.event_time:%H:%M}\n📍 {event.location}\n\n"
    if status == RegistrationStatus.WAITLIST:
        return (
            f"🔥 Вы в листе ожидания\n\n{details}"
            "Сейчас свободных мест нет. Если место освободится, мы автоматически переведём вас в список участников и сообщим об этом.",
            markup,
        )
    return (
        f"🔥 Вы зарегистрированы\n\n{details}Мы напомним вам о встрече заранее.\n\n"
        "Если планы изменятся — пожалуйста, отмените участие. Так ваше место сможет занять другой участник.",
        markup,
    )


async def _claim_notice(
    session: AsyncSession, key: str, settings: Settings | None
) -> tuple[int, str, InlineKeyboardMarkup | None] | None:
    identity = _notice_identity(key)
    async with session.begin():
        event = None
        if identity is not None:
            # Keep the same lock order as the registration and event editor.
            event = await session.scalar(
                select(Event)
                .join(EventRegistration, EventRegistration.event_id == Event.id)
                .where(EventRegistration.id == identity[0])
                .with_for_update(of=Event)
                .execution_options(populate_existing=True)
            )
        row = await session.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.delivery_key == key, NotificationDelivery.notification_type == _NOTICE_TYPE,
                NotificationDelivery.status == "queued",
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        if identity is None or event is None or event.status in _UNAVAILABLE_EVENTS:
            row.status, row.error_code = "skipped", "event_notice_obsolete"
            return None

        registration_id, kind, expected_status, revision = identity
        registration = await session.get(EventRegistration, registration_id, populate_existing=True, with_for_update=True)
        if registration is None or registration.status != expected_status or _revision(registration) != revision:
            row.status, row.error_code = "skipped", "event_notice_obsolete"
            return None
        user = await session.get(User, registration.user_id, populate_existing=True)
        if user is None or user.telegram_id != row.chat_id or user.is_blocked or user.is_archived:
            row.status, row.error_code = "skipped", "event_notice_recipient_changed"
            return None
        experience = await session.get(EventExperience, event.id, populate_existing=True)
        text, markup = await _message(session, settings, kind, event, experience, expected_status)
        row.status = "pending"
        row.attempt_count = 1
        row.last_attempt_at = datetime.now(timezone.utc)
        row.payload_hash = _payload_hash(text)
        return row.chat_id, text, markup


async def deliver_registration_notice(
    session: AsyncSession, key: str, send: Callable[..., Awaitable[object]], settings: Settings | None = None
) -> None:
    """Claim a committed intent, release the database, then attempt Telegram once."""
    try:
        payload = await _claim_notice(session, key, settings)
    except Exception:
        logger.exception("Could not claim event registration notice key=%s", key)
        return
    if payload is None:
        return
    chat_id, text, markup = payload
    message_id = None
    sent_at = None
    try:
        message = await send(chat_id, text, reply_markup=markup)
        observed_id = getattr(message, "message_id", None)
        message_id = observed_id if isinstance(observed_id, int) else None
        status, error_code = "sent", None
        sent_at = datetime.now(timezone.utc)
    except TelegramAPIError as exc:
        status, error_code, _ = _delivery_failure(exc)
    except Exception:
        status, error_code = "uncertain", "delivery_outcome_unknown"
        logger.exception("Event registration notice outcome unknown key=%s", key)

    try:
        async with session.begin():
            await session.execute(
                update(NotificationDelivery)
                .where(
                    NotificationDelivery.delivery_key == key, NotificationDelivery.notification_type == _NOTICE_TYPE,
                    NotificationDelivery.status.in_(("pending", "uncertain")),
                )
                .values(status=status, error_code=error_code, sent_at=sent_at, message_id=message_id)
            )
    except Exception:
        logger.exception("Could not record event registration notice outcome key=%s", key)


async def recover_event_registration_notices(
    bot: Bot, settings: Settings, session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime.now(timezone.utc) - _DELIVERY_LEASE
    async with session_factory() as session, session.begin():
        expired = await session.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.notification_type == _NOTICE_TYPE, NotificationDelivery.status == "pending",
                or_(NotificationDelivery.last_attempt_at.is_(None), NotificationDelivery.last_attempt_at <= cutoff),
            )
            .order_by(NotificationDelivery.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        for row in expired:
            row.status, row.error_code = "uncertain", "delivery_outcome_unknown"
        keys = (await session.scalars(
            select(NotificationDelivery.delivery_key)
            .where(NotificationDelivery.notification_type == _NOTICE_TYPE, NotificationDelivery.status == "queued")
            .order_by(NotificationDelivery.id)
            .limit(100)
        )).all()
    for key in keys:
        async with session_factory() as session:
            await deliver_registration_notice(session, key, bot.send_message, settings)
