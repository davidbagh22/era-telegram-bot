"""Automatic owner Excel after each new event registration.

Same durability contract as ``event_registration_notice_service``: an outbox row
is written in the registration transaction, delivery starts only after commit,
and a scheduler job recovers rows that were not attempted.

Ordering. The event row is locked by ``register_for_event`` until commit, so
outbox ids of one event grow in commit order. The file is always built from the
database at send time, after the claim, and claims for one event are serialized:

* a row is deferred while another row of the same event is in flight;
* a row is superseded when a newer queued row of the same event exists, and the
  newer file names everyone added since the last confirmed send;
* a delivery that fails in an unknown state (network/5xx/crash) is never replayed.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import BufferedInputFile
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import Event, EventRegistration, User
from app.database.system_models import NotificationDelivery
from app.services.event_participants_export import build_participants_xlsx, format_registered_at
from app.services.event_registration_notice_service import _revision
from app.services.event_registration_service import registration_count
from app.services.notification_service import _DELIVERY_LEASE, _delivery_failure, _payload_hash
from app.utils.constants import EventStatus, RegistrationStatus

logger = logging.getLogger(__name__)
NOTICE_TYPE = "event_owner_participants_xlsx"
KEY_PREFIX = "event-owner-xlsx"
MAX_ATTEMPTS = 5
MAX_NAMES_IN_CAPTION = 5
_UNAVAILABLE_EVENTS = {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, EventStatus.CANCELLED}
_ADDED_STATUSES = {RegistrationStatus.REGISTERED, RegistrationStatus.WAITLIST}
_OBSOLETE = "event_owner_export_obsolete"
_SUPERSEDED = "event_owner_export_superseded"

SendDocument = Callable[..., Awaitable[object]]


@dataclass(frozen=True)
class _Payload:
    chat_id: int
    document: bytes
    filename: str
    caption: str
    attempt_count: int


async def resolve_owner_chat(session: AsyncSession, settings: Settings) -> int | None:
    """Private chat of the owner's linked account, or None (fail closed)."""
    if not getattr(settings, "event_registration_owner_excel_enabled", True):
        return None
    explicit = getattr(settings, "event_registration_owner_telegram_id", None)
    chair_id = getattr(settings, "era_chair_user_id", None)
    owner: User | None = None
    if explicit:
        owner = await session.scalar(select(User).where(User.telegram_id == explicit))
    elif chair_id:
        owner = await session.get(User, chair_id)
    else:
        logger.warning("Owner event Excel skipped: no owner account configured")
        return None
    if owner is None or owner.is_blocked or owner.is_archived or not owner.telegram_id:
        logger.warning("Owner event Excel skipped: configured owner account is not an active registered user")
        return None
    return int(owner.telegram_id)


async def _participant_rows(session: AsyncSession, event_id: int) -> list[tuple[EventRegistration, User]]:
    # The registrar's session may hold stale objects; always read current rows.
    result = await session.execute(
        select(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.created_at, EventRegistration.id)
        .execution_options(populate_existing=True)
    )
    return list(result.all())


def _key(registration: EventRegistration) -> str:
    return f"{KEY_PREFIX}:{registration.event_id}:{registration.id}:{registration.status}:{_revision(registration)}"


def _as_utc(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def _identity(key: str) -> tuple[int, int, str, str] | None:
    try:
        prefix, raw_event, raw_registration, status, revision = key.split(":", 4)
        event_id, registration_id = int(raw_event), int(raw_registration)
    except ValueError:
        return None
    if prefix != KEY_PREFIX or event_id <= 0 or registration_id <= 0 or status not in _ADDED_STATUSES:
        return None
    return event_id, registration_id, status, revision


async def _can_deliver(session: AsyncSession, row: NotificationDelivery) -> bool:
    """True when this queued intent still describes a registration that is added right now."""
    identity = _identity(row.delivery_key)
    if identity is None or row.attempt_count >= MAX_ATTEMPTS:
        return False
    event_id, registration_id, expected_status, revision = identity
    registration = await session.get(EventRegistration, registration_id, populate_existing=True)
    return (
        registration is not None
        and registration.event_id == event_id
        and registration.status == expected_status
        and _revision(registration) == revision
    )


async def enqueue_owner_export(
    session: AsyncSession, settings: Settings, registration: EventRegistration
) -> str | None:
    """Store the intent in the registration transaction; repeated calls add nothing."""
    if registration.id is None or registration.status not in _ADDED_STATUSES:
        return None
    try:
        chat_id = await resolve_owner_chat(session, settings)
        if chat_id is None:
            return None
        key = _key(registration)
        existing = await session.scalar(
            select(NotificationDelivery.id).where(NotificationDelivery.delivery_key == key)
        )
        if existing is None:
            session.add(
                NotificationDelivery(
                    delivery_key=key, chat_id=chat_id, notification_type=NOTICE_TYPE,
                    status="queued", attempt_count=0, payload_hash=_payload_hash(key),
                )
            )
        return key
    except Exception:
        logger.exception("Could not enqueue owner event Excel event_id=%s", registration.event_id)
        return None


def _display_name(registration: EventRegistration, user: User | None) -> str:
    signup = registration.signup or {}
    name = signup.get("full_name") or " ".join(
        part for part in ((user.first_name if user else ""), (user.last_name if user else "")) if part
    )
    name = " ".join(str(name or "").split()) or "без имени"
    if registration.status == RegistrationStatus.WAITLIST:
        name += " (лист ожидания)"
    return name


async def _caption(session: AsyncSession, event: Event, added: list[tuple[EventRegistration, User | None]]) -> str:
    names = [_display_name(registration, user) for registration, user in added]
    shown = ", ".join(names[:MAX_NAMES_IN_CAPTION])
    if len(names) > MAX_NAMES_IN_CAPTION:
        shown += f" и ещё {len(names) - MAX_NAMES_IN_CAPTION}"
    registered = await registration_count(session, event.id)
    all_rows = await _participant_rows(session, event.id)
    waitlist = sum(1 for registration, _ in all_rows if registration.status == RegistrationStatus.WAITLIST)
    lines = [
        f"📋 {event.title[:200]}",
        ("Добавлены: " if len(names) > 1 else "Добавлен: ") + shown,
        f"Зарегистрировано: {registered}",
    ]
    if waitlist:
        lines.append(f"В листе ожидания: {waitlist}")
    return "\n".join(lines)[:1024]


def _filename(event_id: int, now: datetime, timezone_name: str) -> str:
    stamp = format_registered_at(now, timezone_name).replace(".", "").replace(":", "").replace(" ", "_")
    return f"ERA_event_{event_id}_participants_{stamp}.xlsx"


async def _claim(session: AsyncSession, key: str, settings: Settings) -> _Payload | None:
    identity = _identity(key)
    if identity is None:
        return None
    event_id, registration_id, expected_status, revision = identity
    prefix = f"{KEY_PREFIX}:{event_id}:"
    async with session.begin():
        event = await session.scalar(
            select(Event).where(Event.id == event_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        row = await session.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.delivery_key == key,
                NotificationDelivery.notification_type == NOTICE_TYPE,
                NotificationDelivery.status == "queued",
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        now = datetime.now(timezone.utc)
        if row.last_attempt_at is not None and _as_utc(row.last_attempt_at) > now:
            return None
        if event is None or event.status in _UNAVAILABLE_EVENTS:
            row.status, row.error_code = "skipped", _OBSOLETE
            return None

        lease_start = now - _DELIVERY_LEASE
        siblings = (await session.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.notification_type == NOTICE_TYPE,
                NotificationDelivery.delivery_key.startswith(prefix),
                NotificationDelivery.id != row.id,
            )
            .order_by(NotificationDelivery.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).all()
        for sibling in siblings:
            stamp = sibling.last_attempt_at
            if stamp is not None and stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if sibling.status == "pending" and stamp is not None and stamp > lease_start:
                return None  # one send per event at a time; a later pass delivers this row
        last_sent_id = max((s.id for s in siblings if s.status == "sent"), default=0)
        for sibling in siblings:
            if sibling.status == "queued" and sibling.id > row.id and await _can_deliver(session, sibling):
                row.status, row.error_code = "skipped", _SUPERSEDED
                return None

        registration = await session.get(EventRegistration, registration_id, populate_existing=True)
        if (
            registration is None or registration.event_id != event_id
            or registration.status != expected_status or _revision(registration) != revision
        ):
            row.status, row.error_code = "skipped", _OBSOLETE
            await _revive_latest_superseded(session, siblings, row, last_sent_id)
            return None
        chat_id = await resolve_owner_chat(session, settings)
        if chat_id is None or chat_id != row.chat_id:
            row.status, row.error_code = "skipped", "event_owner_unresolved"
            return None

        absorbed = [
            s for s in siblings
            if last_sent_id < s.id < row.id
            and (s.status == "queued" or (s.status == "skipped" and s.error_code == _SUPERSEDED))
        ]
        added: list[tuple[EventRegistration, User | None]] = []
        for sibling in absorbed:
            ident = _identity(sibling.delivery_key)
            if sibling.status == "queued":
                sibling.status, sibling.error_code = "skipped", _SUPERSEDED
            other = await session.get(EventRegistration, ident[1], populate_existing=True) if ident else None
            if other is not None and other.status in _ADDED_STATUSES:
                added.append((other, await session.get(User, other.user_id)))
        added.append((registration, await session.get(User, registration.user_id)))

        rows = await _participant_rows(session, event_id)
        now = datetime.now(timezone.utc)
        document = build_participants_xlsx(rows, settings.timezone)
        caption = await _caption(session, event, added)
        row.status = "pending"
        row.attempt_count = (row.attempt_count or 0) + 1
        row.last_attempt_at = now
        row.error_code = None
        row.payload_hash = _payload_hash(caption)
        return _Payload(chat_id, document, _filename(event_id, now, settings.timezone), caption, row.attempt_count)


async def _revive_latest_superseded(
    session: AsyncSession, siblings: list[NotificationDelivery], row: NotificationDelivery, last_sent_id: int,
) -> None:
    """A newer intent went obsolete: the newest older export it displaced must still be sent."""
    for sibling in sorted(siblings, key=lambda s: s.id, reverse=True):
        if (
            last_sent_id < sibling.id < row.id
            and sibling.status == "skipped" and sibling.error_code == _SUPERSEDED
            and await _can_deliver(session, sibling)
        ):
            sibling.status, sibling.error_code = "queued", None
            return


async def deliver_owner_export(
    session: AsyncSession, key: str, send_document: SendDocument, settings: Settings,
) -> None:
    """Claim a committed intent, release the database, then attempt Telegram once."""
    for _ in range(4):
        try:
            payload = await _claim(session, key, settings)
        except Exception:
            logger.exception("Could not claim owner event Excel key=%s", key)
            return
        if payload is None:
            return
        status, error_code, message_id, sent_at, not_before = await _send(payload, send_document, key)
        try:
            async with session.begin():
                values: dict[str, object] = {
                    "status": status, "error_code": error_code, "sent_at": sent_at, "message_id": message_id,
                }
                if status == "queued":
                    values["sent_at"] = None
                    values["last_attempt_at"] = not_before
                    values["attempt_count"] = max(payload.attempt_count - 1, 0)
                await session.execute(
                    update(NotificationDelivery)
                    .where(
                        NotificationDelivery.delivery_key == key,
                        NotificationDelivery.notification_type == NOTICE_TYPE,
                        NotificationDelivery.status == "pending",
                    )
                    .values(**values)
                )
        except Exception:
            logger.exception("Could not record owner event Excel outcome key=%s", key)
            return
        if status == "queued":
            return
        nxt = await _next_queued_key(session, key)
        if nxt is None:
            return
        key = nxt


async def _send(payload: _Payload, send_document: SendDocument, key: str):
    message_id = None
    sent_at = None
    try:
        message = await send_document(
            payload.chat_id,
            document=BufferedInputFile(payload.document, filename=payload.filename),
            caption=payload.caption,
        )
        observed = getattr(message, "message_id", None)
        message_id = observed if isinstance(observed, int) else None
        return "sent", None, message_id, datetime.now(timezone.utc), None
    except TelegramRetryAfter as exc:
        # Telegram refused before sending: retry with a fresh snapshot once its delay has passed.
        not_before = datetime.now(timezone.utc) + timedelta(seconds=max(float(exc.retry_after), 0.0))
        return "queued", "telegram_retry_after", None, None, not_before
    except TelegramAPIError as exc:
        status, error_code, _ = _delivery_failure(exc)
        if status == "uncertain":
            logger.warning("Owner event Excel outcome unknown, not replaying key=%s", key)
        return status, error_code, message_id, sent_at, None
    except Exception:
        logger.exception("Owner event Excel outcome unknown key=%s", key)
        return "uncertain", "delivery_outcome_unknown", None, None, None


def _eligible_now():
    """A queued row with last_attempt_at set is not due until that instant (Telegram retry delay)."""
    return or_(
        NotificationDelivery.last_attempt_at.is_(None),
        NotificationDelivery.last_attempt_at <= datetime.now(timezone.utc),
    )


async def _next_queued_key(session: AsyncSession, key: str) -> str | None:
    identity = _identity(key)
    if identity is None:
        return None
    async with session.begin():
        return await session.scalar(
            select(NotificationDelivery.delivery_key)
            .where(
                NotificationDelivery.notification_type == NOTICE_TYPE,
                NotificationDelivery.delivery_key.startswith(f"{KEY_PREFIX}:{identity[0]}:"),
                NotificationDelivery.status == "queued",
                NotificationDelivery.attempt_count < MAX_ATTEMPTS,
                _eligible_now(),
            )
            .order_by(NotificationDelivery.id.desc())
            .limit(1)
        )


async def recover_owner_exports(
    bot: Bot, settings: Settings, session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime.now(timezone.utc) - _DELIVERY_LEASE
    async with session_factory() as session, session.begin():
        expired = await session.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.notification_type == NOTICE_TYPE, NotificationDelivery.status == "pending",
                or_(NotificationDelivery.last_attempt_at.is_(None), NotificationDelivery.last_attempt_at <= cutoff),
            )
            .order_by(NotificationDelivery.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        for row in expired:
            row.status, row.error_code = "uncertain", "delivery_outcome_unknown"
        exhausted = await session.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.notification_type == NOTICE_TYPE, NotificationDelivery.status == "queued",
                NotificationDelivery.attempt_count >= MAX_ATTEMPTS,
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        for row in exhausted:
            row.status, row.error_code = "failed", "telegram_retry_after"
        keys = (await session.scalars(
            select(NotificationDelivery.delivery_key)
            .where(
                NotificationDelivery.notification_type == NOTICE_TYPE,
                NotificationDelivery.status == "queued",
                _eligible_now(),
            )
            .order_by(NotificationDelivery.id)
            .limit(100)
        )).all()
    for key in keys:
        async with session_factory() as session:
            await deliver_owner_export(session, key, bot.send_document, settings)
