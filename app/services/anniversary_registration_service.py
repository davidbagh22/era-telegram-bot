"""Guest RSVP for the owner's 12 December 2026 anniversary; no membership writes."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, func, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, EventRegistration, User
from app.services.event_registration_policy import registration_is_closed
from app.services.event_registration_service import ACTIVE_REGISTRATION_STATUSES
from app.utils.constants import EventStatus, RegistrationStatus

PAYLOAD = "anniversary2026"
PREFIX = "anniversary:2026:guest:"
START = datetime(2026, 12, 12, 17, 30, tzinfo=ZoneInfo("Asia/Yerevan"))
EVENT_START = START.replace(hour=18, minute=0)
TITLE = "Первая годовщина ЭРА — 1 ГОД"
DETAILS = f"{TITLE}\n12 декабря 2026 · Сбор в 17:30 · Начало в 18:00\nКинозал Дома Москвы в Ереване"
CONSENT = "Подтверждая регистрацию, вы передаёте имя, фамилию, организацию и Telegram ID организаторам для учёта участников."
MENU_BUTTON = "🎟 Зарегистрироваться на годовщину"
MENU_SHORTCUT = f"🎟 Годовщина ЭРА · 12 декабря\n{CONSENT}"
EVENT_TITLES = {
    TITLE.casefold(),
    "первая годовщина эра",
    "12 декабря для эра — особенная дата.",
}
EVENT_MARKER = "[ERA_GUEST_RSVP:anniversary2026]"
OPEN_STATUSES = {EventStatus.APPROVED, EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}
FEATURED_STATUSES = OPEN_STATUSES | {EventStatus.REGISTRATION_CLOSED}
DISPLAY_STATUSES = FEATURED_STATUSES | {EventStatus.ACTIVE, EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}


def registration_open(now: datetime | None = None) -> bool:
    return (now or datetime.now(START.tzinfo)) < START


def is_anniversary(event: Event) -> bool:
    return (
        getattr(event, "event_date", None) == START.date()
        and (
            EVENT_MARKER in (getattr(event, "additional_info", None) or "").splitlines()
            or (event.event_time == time(18) and " ".join(event.title.split()).casefold() in EVENT_TITLES)
        )
    )


def is_public_anniversary(event: Event) -> bool:
    return is_anniversary(event) and event.access_type == "all"


async def find_event(session: AsyncSession) -> Event | None:
    candidates = await session.scalars(select(Event).where(Event.event_date == START.date()))
    matches = [event for event in candidates if is_public_anniversary(event)]
    public = [event for event in matches if event.status in DISPLAY_STATUSES]
    if len(public) == 1:
        return public[0]
    return matches[0] if len(matches) == 1 else None


async def featured_event(session: AsyncSession) -> Event | None:
    if event_has_started():
        return None
    event = await find_event(session)
    if event and event.status in FEATURED_STATUSES and event.access_type == "all":
        return event
    return None


async def menu_available(session: AsyncSession) -> bool:
    if not registration_open():
        return False
    event = await featured_event(session)
    if event is None:
        return False
    experience = await session.get(EventExperience, event.id)
    return event_registration_open(event, experience)


def event_registration_open(event: Event, experience: EventExperience | None) -> bool:
    return (
        registration_open()
        and event.access_type == "all"
        and event.status in OPEN_STATUSES
        and not registration_is_closed(experience)
    )


def event_has_started() -> bool:
    return datetime.now(EVENT_START.tzinfo) >= EVENT_START


def profile_defaults(user: User | None) -> dict[str, str]:
    fields = {
        "first_name": getattr(user, "first_name", None),
        "last_name": getattr(user, "last_name", None),
        "organization": getattr(user, "education_work", None),
    }
    defaults = {}
    for key, value in fields.items():
        try:
            defaults[key] = clean_field(value, name=key != "organization")
        except ValueError:
            continue
    return defaults


async def legacy_registration_status(session: AsyncSession, event: Event | None, user: User | None) -> str | None:
    if event is None or user is None:
        return None
    return await session.scalar(select(EventRegistration.status).where(
        EventRegistration.event_id == event.id,
        EventRegistration.user_id == user.id,
    ))


async def check_event_registration(session: AsyncSession, event: Event, telegram_id: int, user: User | None) -> bool:
    locked_event = await session.scalar(select(Event).where(Event.id == event.id)
        .with_for_update().execution_options(populate_existing=True))
    if (
        locked_event is None or not is_public_anniversary(locked_event) or locked_event.status not in FEATURED_STATUSES
    ):
        raise ValueError("event_not_found")
    legacy_status = await legacy_registration_status(session, locked_event, user)
    if await get_registration(session, telegram_id) or legacy_status in ACTIVE_REGISTRATION_STATUSES:
        return True
    if legacy_status == RegistrationStatus.WAITLIST:
        raise ValueError("anniversary_waitlisted")
    experience = await session.get(EventExperience, event.id, populate_existing=True)
    if not event_registration_open(locked_event, experience):
        raise ValueError("anniversary_registration_closed")
    if locked_event.participant_limit is not None and await attendee_count(session, locked_event) >= locked_event.participant_limit:
        raise ValueError("full")
    return False


def clean_field(value: str, *, name: bool = False) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError("Введите ответ одной строкой.")
    value = " ".join(value.split())
    if not value or len(value) > (80 if name else 160) or value.startswith("/"):
        raise ValueError("Введите короткий ответ: до 80 символов для имени и фамилии, до 160 для организации.")
    if name and not any(c.isalpha() for c in value):
        raise ValueError("Укажите имя или фамилию буквами.")
    return value


async def get_registration(session: AsyncSession, telegram_id: int) -> dict | None:
    return await session.scalar(select(AppSetting.value).where(AppSetting.key == f"{PREFIX}{telegram_id}"))


async def register(session: AsyncSession, telegram_id: int, data: dict) -> dict:
    if not registration_open():
        raise ValueError("Регистрация на годовщину завершена.")
    value = {
        "first_name": clean_field(data.get("first_name"), name=True),
        "last_name": clean_field(data.get("last_name"), name=True),
        "organization": clean_field(data.get("organization")),
        "telegram_id": telegram_id,
        "registered_at": datetime.now(START.tzinfo).isoformat(),
        "consent_version": "anniversary2026-v1",
    }
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise RuntimeError("Unsupported RSVP database")
    await session.execute(insert(AppSetting).values(key=f"{PREFIX}{telegram_id}", value=value)
                          .on_conflict_do_nothing(index_elements=["key"]))
    # Persist before sending success: a failed Telegram reply cannot lose the RSVP.
    await session.commit()
    return await get_registration(session, telegram_id)


async def roster(session: AsyncSession) -> list[dict]:
    entries = {row["telegram_id"]: row for row in await session.scalars(
        select(AppSetting.value).where(AppSetting.key.startswith(PREFIX)).order_by(AppSetting.key)
    )}
    event = await find_event(session)
    if event is not None:
        rows = await session.execute(
            select(User, EventRegistration).join(EventRegistration, User.id == EventRegistration.user_id)
            .where(EventRegistration.event_id == event.id, EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES))
            .order_by(EventRegistration.id)
        )
        for user, registration in rows:
            entries.setdefault(user.telegram_id, {
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "last_name": user.last_name or "",
                "organization": user.education_work or "",
                "registered_at": registration.created_at.isoformat(),
            })
    return list(entries.values())


async def attendee_count(session: AsyncSession, event: Event) -> int:
    legacy_key = literal(PREFIX) + cast(User.telegram_id, String)
    guest_keys = select(AppSetting.key).where(AppSetting.key.startswith(PREFIX))
    legacy_keys = (
        select(legacy_key).join(EventRegistration, User.id == EventRegistration.user_id)
        .where(EventRegistration.event_id == event.id, EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES))
    )
    return int(await session.scalar(select(func.count()).select_from(guest_keys.union(legacy_keys).subquery())) or 0)
