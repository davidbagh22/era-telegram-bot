"""Post-event certificate review: the owner decides, then each certificate goes out once.

When an event ends, its owner and responsible person get one notice with the
title, date, number of registrations and a button to choose recipients. Nothing
is issued or sent to participants until an authorized person confirms. Issuing
goes through ``certificate_service`` and delivery through its outbox
(``event-certificate:pending:*``), whose sender makes one attempt and never
replays an uncertain send.

State lives in one ``AppSetting`` row per event (``post-event-certs:review:<id>``);
the unique key makes the request itself idempotent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.certificate_models import CertificateIssue
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, EventRegistration, User
from app.services import certificate_service
from app.services.authorization_service import can_manage_events, is_full_admin
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus

logger = logging.getLogger(__name__)

REVIEW_PREFIX = "post-event-certs:review:"
NOTICE_PENDING_PREFIX = "post-event-certs:notice-pending:"
NOTICE_DONE_PREFIX = "post-event-certs:notice-done:"
NOTICE_TYPE = "post_event_certificate_review"
# Only freshly ended events are announced one by one; older ones get a single
# one-time summary instead (``BACKFILL_KEY``).
RECENT_WINDOW = timedelta(days=3)
BACKFILL_KEY = "post-event-certs:backfill:v1"
END_GRACE = timedelta(hours=1)
DEFAULT_DURATION = timedelta(hours=3)
EXCLUDED_EVENT_STATUSES = (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, EventStatus.CANCELLED)
NOTICES_PER_RUN = 20


class ReviewError(ValueError):
    """User-facing refusal; the message is shown as is."""


class StaleReview(ReviewError):
    pass


@dataclass(frozen=True)
class Candidate:
    user_id: int
    name: str
    status: str
    eligible: bool
    certificate_id: int | None = None
    certificate_status: str | None = None

    @property
    def attended(self) -> bool:
        return self.status == RegistrationStatus.ATTENDED

    @property
    def selectable(self) -> bool:
        return self.eligible and self.certificate_id is None


@dataclass
class ConfirmResult:
    issued: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


@dataclass
class DeliverySummary:
    sent: int = 0
    pending: int = 0
    skipped: int = 0
    not_queued: int = 0
    attention: list[str] = field(default_factory=list)


def review_key(event_id: int) -> str:
    return f"{REVIEW_PREFIX}{event_id}"


def event_ends_at(event: Event, experience: EventExperience | None, tz_name: str) -> datetime:
    """UTC moment after which the event counts as over, with a short grace period."""
    tz = ZoneInfo(tz_name)
    start = event.event_time or time(0)
    end_time = getattr(experience, "end_time", None)
    if end_time is None:
        end = datetime.combine(event.event_date, start, tz) + DEFAULT_DURATION
    elif end_time >= start:
        end = datetime.combine(event.event_date, end_time, tz)
    else:
        end = datetime.combine(event.event_date + timedelta(days=1), end_time, tz)
    return (end + END_GRACE).astimezone(timezone.utc)


def _active(user: User | None) -> bool:
    return bool(user and not user.is_blocked and not user.is_archived and user.telegram_id)


async def configured_owner(session, settings) -> User | None:
    """Same owner account as the registration Excel; never inferred from ADMIN_IDS."""
    explicit = getattr(settings, "event_registration_owner_telegram_id", None)
    chair_id = getattr(settings, "era_chair_user_id", None)
    owner = None
    if explicit:
        owner = await session.scalar(select(User).where(User.telegram_id == explicit))
    elif chair_id:
        owner = await session.get(User, chair_id)
    return owner if _active(owner) else None


_ALL_EVENTS = object()


async def _review_scope(session, actor: User | None, settings):
    """``_ALL_EVENTS``, the actor's id (own events only), or ``None`` (nothing)."""
    if actor is None:
        return None
    actor = await session.scalar(select(User).where(User.id == actor.id).execution_options(populate_existing=True))
    if not _active(actor):
        return None
    if is_full_admin(actor, settings, actor.telegram_id) or can_manage_events(actor, settings, actor.telegram_id):
        return _ALL_EVENTS
    if actor.application_status != ApplicationStatus.APPROVED:
        return None
    owner = await configured_owner(session, settings)
    if owner is not None and owner.id == actor.id:
        return _ALL_EVENTS
    return actor.id


def _in_scope(scope, event: Event) -> bool:
    return scope is _ALL_EVENTS or (scope is not None and event.responsible_id == scope)


async def can_review(session, actor: User | None, settings, event: Event | None) -> bool:
    if event is None:
        return False
    return _in_scope(await _review_scope(session, actor, settings), event)


async def notice_recipients(session, settings, event: Event) -> list[User]:
    people: list[User] = []
    owner = await configured_owner(session, settings)
    if owner is not None:
        people.append(owner)
    if event.responsible_id:
        responsible = await session.get(User, event.responsible_id)
        if (_active(responsible) and responsible.application_status == ApplicationStatus.APPROVED
                and all(p.id != responsible.id for p in people)):
            people.append(responsible)
    return people


def _display_name(registration: EventRegistration, user: User) -> str:
    signup = registration.signup or {}
    name = signup.get("full_name") or f"{user.first_name or ''} {user.last_name or ''}"
    return " ".join(str(name).split()) or "без имени"


async def candidates(session, event_id: int) -> list[Candidate]:
    rows = (await session.execute(
        select(EventRegistration, User).join(User, User.id == EventRegistration.user_id)
        .where(EventRegistration.event_id == event_id,
               EventRegistration.status.in_(certificate_service.POST_EVENT_STATUSES))
        .execution_options(populate_existing=True)
    )).all()
    latest: dict[int, CertificateIssue] = {}
    for issue in await session.scalars(
        select(CertificateIssue).where(CertificateIssue.event_id == event_id).order_by(CertificateIssue.revision)
    ):
        latest[issue.user_id] = issue
    people = []
    for registration, user in rows:
        issue = latest.get(user.id)
        people.append(Candidate(
            user_id=user.id, name=_display_name(registration, user), status=registration.status,
            eligible=(user.application_status == ApplicationStatus.APPROVED
                      and not user.is_blocked and not user.is_archived),
            certificate_id=issue.id if issue else None,
            certificate_status=issue.status if issue else None,
        ))
    return sorted(people, key=lambda c: (c.name.casefold(), c.user_id))


async def load_review(session, event_id: int, *, for_update: bool = False) -> AppSetting | None:
    query = select(AppSetting).where(AppSetting.key == review_key(event_id))
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(query)


async def ensure_review(session, event: Event, *, source: str, now: datetime | None = None,
                        notify: bool = True) -> AppSetting | None:
    """Create the event's single review request; ``None`` when it exists or nobody qualifies."""
    if await load_review(session, event.id) is not None:
        return None
    people = await candidates(session, event.id)
    if not people:
        return None
    selectable = [c for c in people if c.selectable]
    value = {
        "state": "open" if selectable else "covered",
        "selected": [c.user_id for c in selectable if c.attended],
        "waiting": len(selectable),
        "rev": 0,
        "source": source,
        "created_at": (now or datetime.now(timezone.utc)).isoformat(),
        "history": [],
    }
    row = AppSetting(key=review_key(event.id), value=value)
    try:
        async with session.begin_nested():
            session.add(row)
            if selectable and notify:
                session.add(AppSetting(key=f"{NOTICE_PENDING_PREFIX}{event.id}", value={"event_id": event.id}))
    except IntegrityError:
        return None
    return row


async def _authorized_review(session, actor, settings, event_id: int) -> tuple[Event, AppSetting]:
    event = await session.get(Event, event_id)
    if not await can_review(session, actor, settings, event):
        raise PermissionError("post_event_certificates_denied")
    row = await load_review(session, event_id, for_update=True)
    if row is None:
        raise ReviewError("Запрос на выдачу сертификатов для этого мероприятия не найден.")
    return event, row


async def change_selection(session, actor, settings, event_id: int, mode: str, user_id: int | None = None) -> AppSetting:
    """``mode``: toggle / all / none / attended. Unselectable people are never kept selected."""
    _event, row = await _authorized_review(session, actor, settings, event_id)
    people = await candidates(session, event_id)
    selectable = {c.user_id for c in people if c.selectable}
    selected = set(row.value.get("selected") or []) & selectable
    if mode == "toggle":
        if user_id not in selectable:
            raise ReviewError("Этого участника нельзя отметить: сертификат уже есть или участник недоступен.")
        selected ^= {user_id}
    elif mode == "all":
        selected = selectable
    elif mode == "none":
        selected = set()
    elif mode == "attended":
        selected = {c.user_id for c in people if c.selectable and c.attended}
    else:
        raise ValueError(f"unknown selection mode {mode!r}")
    row.value = {**row.value, "selected": sorted(selected), "rev": int(row.value.get("rev") or 0) + 1,
                 "state": "open"}
    return row


async def set_hidden(session, actor, settings, event_id: int, hidden: bool) -> AppSetting:
    _event, row = await _authorized_review(session, actor, settings, event_id)
    row.value = {**row.value, "state": "dismissed" if hidden else "open"}
    return row


async def _ensure_still_over(session, event: Event, settings) -> None:
    """A request made before a reschedule or cancellation must not issue anything."""
    if event.status in EXCLUDED_EVENT_STATUSES:
        raise ReviewError("Мероприятие отменено или не опубликовано, выдача недоступна.")
    experience = await session.get(EventExperience, event.id)
    if event_ends_at(event, experience, settings.timezone) > datetime.now(timezone.utc):
        raise ReviewError("Мероприятие ещё не закончилось: дата или время изменились, выдача недоступна.")


async def confirm(session, actor, settings, event_id: int, rev: int) -> ConfirmResult:
    """Issue to the confirmed selection once; a repeated or outdated press issues nothing."""
    event, row = await _authorized_review(session, actor, settings, event_id)
    if int(row.value.get("rev") or 0) != rev:
        raise StaleReview("Список уже изменился или выдача уже подтверждена. Откройте его заново.")
    await _ensure_still_over(session, event, settings)
    selected = list(row.value.get("selected") or [])
    if not selected:
        raise ReviewError("Никто не выбран.")
    by_id = {c.user_id: c for c in await candidates(session, event_id)}
    result = ConfirmResult()
    for user_id in selected:
        person = by_id.get(user_id)
        if person is None or not person.eligible:
            result.skipped.append(person.name if person else f"#{user_id}")
            continue
        if person.certificate_id is not None:
            result.already.append(person.name)
            continue
        try:
            async with session.begin_nested():
                _issue, created = await certificate_service.issue_post_event_certificate(
                    session, actor, user_id=user_id, event_id=event_id)
        except ValueError:
            logger.warning("Post-event certificate refused event_id=%s user_id=%s", event_id, user_id)
            result.skipped.append(person.name)
            continue
        (result.issued if created else result.already).append(person.name)
    history = list(row.value.get("history") or [])
    history.append({"at": datetime.now(timezone.utc).isoformat(), "by": actor.id, "issued": len(result.issued),
                    "already": len(result.already), "skipped": len(result.skipped)})
    row.value = {**row.value, "selected": [], "rev": rev + 1, "state": "open", "history": history[-20:]}
    return result


async def delivery_summary(session, event_id: int) -> DeliverySummary:
    issues = list(await session.scalars(select(CertificateIssue).where(
        CertificateIssue.event_id == event_id, CertificateIssue.status == "issued")))
    summary = DeliverySummary()
    if not issues:
        return summary
    keys = [key for issue in issues for key in certificate_service.delivery_keys(issue.id)]
    states = {}
    for key in await session.scalars(select(AppSetting.key).where(AppSetting.key.in_(keys))):
        _prefix, state, raw_id = key.split(":", 2)
        states[int(raw_id)] = state
    names = {c.certificate_id: c.name for c in await candidates(session, event_id) if c.certificate_id}
    for issue in issues:
        state = states.get(issue.id)
        if state == "sent":
            summary.sent += 1
        elif state == "pending":
            summary.pending += 1
        elif state == "skipped":
            summary.skipped += 1
        elif state == "needs_attention":
            summary.attention.append(names.get(issue.id) or issue.document_number)
        else:
            summary.not_queued += 1
    return summary


async def list_reviews(session, actor, settings, *, hidden: bool = False) -> list[tuple[Event, dict]]:
    scope = await _review_scope(session, actor, settings)
    if scope is None:
        return []
    wanted = "dismissed" if hidden else "open"
    values: dict[int, dict] = {}
    for row in await session.scalars(select(AppSetting).where(AppSetting.key.like(f"{REVIEW_PREFIX}%"))):
        raw_id = row.key.removeprefix(REVIEW_PREFIX)
        if raw_id.isdigit() and (row.value or {}).get("state") == wanted:
            values[int(raw_id)] = row.value
    if not values:
        return []
    events = await session.scalars(select(Event).where(Event.id.in_(list(values)))
                                   .order_by(Event.event_date.desc(), Event.id.desc()))
    return [(event, values[event.id]) for event in events if _in_scope(scope, event)]


def notice_text(event: Event, people: list[Candidate]) -> str:
    attended = sum(1 for c in people if c.attended)
    covered = sum(1 for c in people if c.certificate_id is not None)
    lines = [
        "🎓 Мероприятие прошло — кому выдать сертификат?",
        "",
        event.title[:200],
        f"{event.event_date:%d.%m.%Y}" + (f", {event.event_time:%H:%M}" if event.event_time else ""),
        f"Зарегистрировались: {len(people)}",
    ]
    if attended:
        lines.append(f"Отметили присутствие: {attended}")
    if covered:
        lines.append(f"Сертификат уже есть: {covered}")
    lines += ["", "Откройте список и отметьте участников. Пока вы не подтвердите выдачу, "
                  "участникам ничего не отправляется."]
    return "\n".join(lines)


def notice_markup(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Выбрать участников", callback_data=f"pec:v:{event_id}:0")]])


async def scan_ended_events(bot, settings, session_factory, *, now: datetime | None = None) -> None:
    if not getattr(settings, "post_event_certificate_review_enabled", True):
        return
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(settings.timezone)
    earliest = (now - RECENT_WINDOW).astimezone(tz).date() - timedelta(days=1)
    async with session_factory() as session:
        events = list(await session.scalars(
            select(Event).where(Event.event_date >= earliest, Event.event_date <= now.astimezone(tz).date(),
                                Event.status.not_in(EXCLUDED_EVENT_STATUSES))
            .order_by(Event.event_date, Event.id)))
        known = set(await session.scalars(select(AppSetting.key).where(
            AppSetting.key.in_([review_key(e.id) for e in events])))) if events else set()
        for event in events:
            if review_key(event.id) in known:
                continue
            ends = event_ends_at(event, await session.get(EventExperience, event.id), settings.timezone)
            if now - RECENT_WINDOW <= ends <= now:
                await ensure_review(session, event, source="scheduler", now=now)
        await backfill_past_events(session, settings, now)
        await session.commit()
    await deliver_review_notices(bot, settings, session_factory)
    await deliver_backfill_digest(bot, settings, session_factory)


async def backfill_past_events(session, settings, now: datetime) -> AppSetting | None:
    """Run once: the same requests for events that ended before the regular window.

    No per-event notices and nothing to participants; the owner gets one summary
    and confirms each event separately. Events where everyone already has a
    certificate stay ``covered`` and are not listed.
    """
    if await session.scalar(select(AppSetting.id).where(AppSetting.key == BACKFILL_KEY)):
        return None
    cutoff = now - RECENT_WINDOW
    events = await session.scalars(
        select(Event).where(Event.event_date <= cutoff.astimezone(ZoneInfo(settings.timezone)).date(),
                            Event.status.not_in(EXCLUDED_EVENT_STATUSES))
        .order_by(Event.event_date, Event.id))
    opened, waiting = 0, 0
    for event in list(events):
        if event_ends_at(event, await session.get(EventExperience, event.id), settings.timezone) >= cutoff:
            continue
        row = await ensure_review(session, event, source="backfill", now=now, notify=False)
        if row is not None and row.value["state"] == "open":
            opened += 1
            waiting += row.value["waiting"]
    marker = AppSetting(key=BACKFILL_KEY, value={"at": now.isoformat(), "events": opened, "people": waiting,
                                                 "digest": "pending" if opened else "none"})
    try:
        async with session.begin_nested():
            session.add(marker)
    except IntegrityError:
        return None
    return marker


def backfill_text(events: int, people: int) -> str:
    return ("🎓 Сертификаты за прошедшие мероприятия\n\n"
            f"Прошедших мероприятий, где сертификаты ещё не выданы: {events}\n"
            f"Участников без сертификата: {people}\n\n"
            "Откройте список, по каждому мероприятию отметьте участников и подтвердите выдачу. "
            "Без вашего подтверждения участникам ничего не отправляется.")


async def deliver_backfill_digest(bot, settings, session_factory) -> None:
    from app.services.notification_service import safe_send_once

    async with session_factory() as session:
        marker = await session.scalar(select(AppSetting).where(AppSetting.key == BACKFILL_KEY)
                                      .with_for_update(skip_locked=True))
        if marker is None or (marker.value or {}).get("digest") != "pending":
            return
        owner = await configured_owner(session, settings)
        outcome = "no_recipient"
        if owner is not None:
            result = await safe_send_once(
                bot, settings, owner.telegram_id, backfill_text(marker.value["events"], marker.value["people"]),
                delivery_key=f"{BACKFILL_KEY}:digest:{owner.telegram_id}", notification_type=NOTICE_TYPE,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Открыть список", callback_data="pec:l:0:o")]]),
                max_attempts=2)
            outcome = result.status
        if outcome != "sent":
            logger.warning("Post-event certificate backfill summary not confirmed outcome=%s", outcome)
        marker.value = {**marker.value, "digest": "done", "digest_outcome": outcome}
        await session.commit()


async def deliver_review_notices(bot, settings, session_factory) -> None:
    from app.services.notification_service import safe_send_once

    async with session_factory() as session:
        rows = list(await session.scalars(
            select(AppSetting).where(AppSetting.key.like(f"{NOTICE_PENDING_PREFIX}%"))
            .order_by(AppSetting.id).limit(NOTICES_PER_RUN).with_for_update(skip_locked=True)))
        for row in rows:
            event_id = (row.value or {}).get("event_id")
            event = await session.get(Event, event_id) if isinstance(event_id, int) else None
            review = await load_review(session, event_id) if event is not None else None
            outcome = "obsolete"
            if event is not None and review is not None and review.value.get("state") == "open":
                text = notice_text(event, await candidates(session, event.id))
                recipients = await notice_recipients(session, settings, event)
                statuses = []
                for person in recipients:
                    result = await safe_send_once(
                        bot, settings, person.telegram_id, text,
                        delivery_key=f"post-event-certs:notice:{event.id}:{person.telegram_id}",
                        notification_type=NOTICE_TYPE, reply_markup=notice_markup(event.id), max_attempts=2)
                    statuses.append(result.status)
                outcome = ("sent" if "sent" in statuses else "needs_attention") if recipients else "no_recipient"
                if outcome != "sent":
                    logger.warning("Post-event certificate notice not confirmed event_id=%s outcome=%s",
                                   event.id, outcome)
            row.key = f"{NOTICE_DONE_PREFIX}{event_id if isinstance(event_id, int) else f'row{row.id}'}"
            row.value = {**(row.value or {}), "outcome": outcome}
        await session.commit()
