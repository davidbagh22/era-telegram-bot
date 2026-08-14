"""Annual editorial ritual for the registered ``general`` Telegram chat.

The content itself lives under content/general_chat/*.json.  This module owns
planning, priority, persistence, idempotent delivery and admin overrides.  It
never falls back to a hard-coded chat id or another system chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.autocontent_models import (
    GeneralContentDelivery,
    GeneralContentOverride,
    GeneralCustomContent,
)
from app.database.models import AppSetting
from app.services.chat_registry_service import list_chat_registry
from app.services.notification_service import notify_admins

logger = logging.getLogger(__name__)

Slot = Literal["morning", "evening"]
ContentType = Literal["morning_quote", "evening_quote", "weekly_challenge", "monthly_theme", "holiday"]

CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content" / "general_chat"
AUTOCONTENT_SETTINGS_KEY = "general_autocontent.settings"
GENERAL_CHAT_KEY = "general"
MORNING_TIME = time(9, 0)
EVENING_TIME = time(18, 0)
QUOTE_LATE_LIMIT = timedelta(minutes=60)
SIGNIFICANT_LATE_LIMIT = timedelta(hours=6)
MAX_SEND_ATTEMPTS = 3
TERMINAL_STATUSES = {"sent", "skipped_late", "missed", "skipped_admin", "disabled", "failed"}

DEFAULT_AUTOCONTENT_SETTINGS: dict[str, bool] = {
    "paused": False,
    "quotes": True,
    "challenges": True,
    "themes": True,
    "holidays": True,
}

TYPE_SETTING_KEY = {
    "morning_quote": "quotes",
    "evening_quote": "quotes",
    "weekly_challenge": "challenges",
    "monthly_theme": "themes",
    "holiday": "holidays",
}


@dataclass(frozen=True)
class ContentItem:
    content_id: str
    content_type: ContentType
    slot: Slot
    text: str
    title: str | None = None
    date_key: str | None = None
    source: str = "pack"


@dataclass(frozen=True)
class PlannedContent:
    item: ContentItem
    planned_at: datetime
    effective_text: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self.item)
        payload.update(
            planned_at=self.planned_at.isoformat(),
            effective_text=self.effective_text,
        )
        return payload


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    content_id: str | None
    delivery_id: int | None = None
    message_id: int | None = None


@dataclass(frozen=True)
class _CandidateResolution:
    item: ContentItem | None
    blocked: bool = False


def _read_json(filename: str) -> Any:
    return json.loads((CONTENT_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _pack() -> dict[str, Any]:
    return {
        "quotes": _read_json("quotes.json"),
        "challenges": _read_json("weekly_challenges.json"),
        "themes": _read_json("monthly_themes.json"),
        "holidays": _read_json("holidays.json"),
    }


def clear_content_cache() -> None:
    _pack.cache_clear()


def _date_key(day: date) -> str:
    return day.strftime("%m-%d")


def _quote_for(day: date, slot: Slot) -> ContentItem | None:
    key = _date_key(day)
    field = "morning" if slot == "morning" else "evening"
    content_type: ContentType = "morning_quote" if slot == "morning" else "evening_quote"
    for row in _pack()["quotes"]["items"]:
        if row["date_key"] == key:
            block = row[field]
            return ContentItem(
                content_id=block["id"],
                content_type=content_type,
                slot=slot,
                text=block["text"],
                date_key=key,
            )
    # 29 February is intentionally not part of the 365-entry pack.  Reuse a
    # neighbouring editorial slot only on leap day rather than crashing.
    if key == "02-29":
        return _quote_for(day.replace(day=28), slot)
    return None


def _static_holiday(day: date) -> ContentItem | None:
    key = _date_key(day)
    for row in _pack()["holidays"]["items"]:
        if row["date_key"] == key:
            return ContentItem(
                content_id=row["id"],
                content_type="holiday",
                slot="morning",
                text=row["text"],
                title=row.get("title"),
                date_key=key,
            )
    return None


def _monthly_theme(month: int) -> ContentItem | None:
    for row in _pack()["themes"]["items"]:
        if int(row["month"]) == month:
            return ContentItem(
                content_id=row["id"],
                content_type="monthly_theme",
                slot="morning",
                text=row["text"],
                title=row.get("title"),
                date_key=f"month:{month:02d}",
            )
    return None


def _weekly_challenge(day: date) -> ContentItem | None:
    rows = _pack()["challenges"]["items"]
    exact = next((row for row in rows if row.get("date") == day.isoformat()), None)
    if exact is None and rows:
        first = date.fromisoformat(rows[0]["date"])
        week_offset = (day - first).days // 7
        exact = rows[week_offset % len(rows)]
    if exact is None:
        return None
    return ContentItem(
        content_id=exact["id"],
        content_type="weekly_challenge",
        slot="evening",
        text=exact["text"],
        title=exact.get("title", "Вызов ЭРА на эту неделю"),
        date_key=exact.get("date"),
    )


def static_item_by_id(content_id: str) -> ContentItem | None:
    for row in _pack()["quotes"]["items"]:
        for field, content_type, slot in (
            ("morning", "morning_quote", "morning"),
            ("evening", "evening_quote", "evening"),
        ):
            block = row[field]
            if block["id"] == content_id:
                return ContentItem(
                    content_id=content_id,
                    content_type=content_type,  # type: ignore[arg-type]
                    slot=slot,  # type: ignore[arg-type]
                    text=block["text"],
                    date_key=row["date_key"],
                )
    for filename, content_type, slot in (
        ("challenges", "weekly_challenge", "evening"),
        ("themes", "monthly_theme", "morning"),
        ("holidays", "holiday", "morning"),
    ):
        for row in _pack()[filename]["items"]:
            if row["id"] == content_id:
                return ContentItem(
                    content_id=content_id,
                    content_type=content_type,  # type: ignore[arg-type]
                    slot=slot,  # type: ignore[arg-type]
                    text=row["text"],
                    title=row.get("title"),
                    date_key=row.get("date_key") or row.get("date") or (f"month:{int(row['month']):02d}" if "month" in row else None),
                )
    return None


async def get_autocontent_settings(session: AsyncSession) -> dict[str, bool]:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == AUTOCONTENT_SETTINGS_KEY))
    value = row.value if row and isinstance(row.value, dict) else {}
    return {key: bool(value.get(key, default)) for key, default in DEFAULT_AUTOCONTENT_SETTINGS.items()}


async def update_autocontent_settings(
    session: AsyncSession,
    changes: dict[str, bool],
    *,
    actor_id: int | None,
) -> dict[str, bool]:
    unknown = set(changes) - set(DEFAULT_AUTOCONTENT_SETTINGS)
    if unknown:
        raise ValueError(f"unknown_settings:{','.join(sorted(unknown))}")
    current = await get_autocontent_settings(session)
    current.update({key: bool(value) for key, value in changes.items()})
    row = await session.scalar(select(AppSetting).where(AppSetting.key == AUTOCONTENT_SETTINGS_KEY))
    if row is None:
        row = AppSetting(key=AUTOCONTENT_SETTINGS_KEY, value=current, updated_by=actor_id)
        session.add(row)
    else:
        row.value = current
        row.updated_by = actor_id
    await session.commit()
    return current


async def _custom_holiday(session: AsyncSession, day: date) -> ContentItem | None:
    keys = (_date_key(day), day.isoformat())
    row = await session.scalar(
        select(GeneralCustomContent)
        .where(
            GeneralCustomContent.content_type == "holiday",
            GeneralCustomContent.date_key.in_(keys),
            GeneralCustomContent.is_enabled.is_(True),
        )
        .order_by(GeneralCustomContent.updated_at.desc(), GeneralCustomContent.id.desc())
    )
    if row is None:
        return None
    return ContentItem(
        content_id=row.content_id,
        content_type="holiday",
        slot="morning",
        text=row.text,
        title=row.title,
        date_key=row.date_key,
        source="custom",
    )


async def _has_holiday(session: AsyncSession, day: date) -> bool:
    return bool(await _custom_holiday(session, day) or _static_holiday(day))


async def _theme_due_today(session: AsyncSession, day: date, holiday_enabled: bool) -> bool:
    if day.day > 3:
        return False
    first = day.replace(day=1)
    for offset in range(3):
        candidate = first + timedelta(days=offset)
        occupied = holiday_enabled and await _has_holiday(session, candidate)
        if not occupied:
            return candidate == day
    # All first three mornings are occupied by holidays: max deferral is +2,
    # so theme is not silently moved further into the month.
    return False


async def _override_resolution(session: AsyncSession, item: ContentItem) -> _CandidateResolution:
    if item.source == "custom":
        return _CandidateResolution(item=item)
    override = await session.scalar(
        select(GeneralContentOverride).where(GeneralContentOverride.content_id == item.content_id)
    )
    if override is None:
        return _CandidateResolution(item=item)
    if override.is_skipped:
        return _CandidateResolution(item=None, blocked=True)
    if not override.is_enabled:
        return _CandidateResolution(item=None, blocked=False)
    if override.override_text:
        item = ContentItem(
            content_id=item.content_id,
            content_type=item.content_type,
            slot=item.slot,
            text=override.override_text,
            title=item.title,
            date_key=item.date_key,
            source=item.source,
        )
    return _CandidateResolution(item=item)


async def _candidate_items(
    session: AsyncSession,
    day: date,
    slot: Slot,
    flags: dict[str, bool],
) -> list[ContentItem]:
    candidates: list[ContentItem] = []
    if slot == "morning":
        if flags["holidays"]:
            custom = await _custom_holiday(session, day)
            static = _static_holiday(day)
            if custom:
                candidates.append(custom)
            if static and (not custom or custom.content_id != static.content_id):
                candidates.append(static)
        if flags["themes"] and await _theme_due_today(session, day, flags["holidays"]):
            theme = _monthly_theme(day.month)
            if theme:
                candidates.append(theme)
        if flags["quotes"]:
            quote = _quote_for(day, "morning")
            if quote:
                candidates.append(quote)
        return candidates

    if day.weekday() == 6 and flags["challenges"]:
        challenge = _weekly_challenge(day)
        if challenge:
            candidates.append(challenge)
    if flags["quotes"]:
        quote = _quote_for(day, "evening")
        if quote:
            candidates.append(quote)
    return candidates


async def plan_content(
    session: AsyncSession,
    day: date,
    slot: Slot,
    *,
    timezone_name: str,
) -> PlannedContent | None:
    flags = await get_autocontent_settings(session)
    if flags["paused"]:
        return None
    planned_time = MORNING_TIME if slot == "morning" else EVENING_TIME
    planned_at = datetime.combine(day, planned_time, tzinfo=ZoneInfo(timezone_name))
    for candidate in await _candidate_items(session, day, slot, flags):
        resolution = await _override_resolution(session, candidate)
        if resolution.blocked:
            return None
        if resolution.item is not None:
            return PlannedContent(
                item=resolution.item,
                planned_at=planned_at,
                effective_text=resolution.item.text,
            )
    return None


def scheduled_idempotency_key(day: date, slot: Slot, content_type: str) -> str:
    return f"general_content:{day.isoformat()}:{slot}:{content_type}"


def _late_status(item: ContentItem, planned_at: datetime, now: datetime) -> str | None:
    lateness = now - planned_at
    if lateness <= timedelta(0):
        return None
    if item.content_type in {"morning_quote", "evening_quote"}:
        return "skipped_late" if lateness > QUOTE_LATE_LIMIT else None
    return "missed" if lateness > SIGNIFICANT_LATE_LIMIT else None


async def _general_chat_id(session: AsyncSession, settings: Settings) -> int | None:
    entries = await list_chat_registry(session, settings)
    entry = next((item for item in entries if item.chat_key == GENERAL_CHAT_KEY), None)
    return entry.chat_id if entry and entry.is_bound else None


async def _send_with_retry(bot: Bot, chat_id: int, text: str) -> tuple[Any | None, int, str | None, bool]:
    attempt = 0
    while attempt < MAX_SEND_ATTEMPTS:
        attempt += 1
        try:
            message = await bot.send_message(chat_id, text, parse_mode="HTML")
            return message, attempt, None, False
        except TelegramRetryAfter as exc:
            if attempt >= MAX_SEND_ATTEMPTS:
                return None, attempt, "retry_after", True
            await asyncio.sleep(min(max(float(exc.retry_after), 0.0), 30.0))
        except (TelegramNetworkError, TelegramServerError):
            if attempt >= MAX_SEND_ATTEMPTS:
                return None, attempt, "telegram_transient", True
            await asyncio.sleep(min(2**attempt, 10))
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            return None, attempt, exc.__class__.__name__, False
        except TelegramAPIError as exc:
            return None, attempt, exc.__class__.__name__, False
    return None, attempt, "telegram_unknown", False


async def _alert_delivery_failure(bot: Bot, settings: Settings, code: str, content_id: str) -> None:
    await notify_admins(
        bot,
        settings,
        "⚠️ Автоконтент ЭРА не отправлен.\n"
        f"Причина: {code}\n"
        f"Материал: {content_id}\n"
        "Проверьте Admin Mode → Связь → Автоконтент.",
    )


async def deliver_planned_content(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    planned: PlannedContent,
    *,
    now: datetime,
    manual: bool = False,
) -> DeliveryOutcome:
    item = planned.item
    if manual:
        idempotency_key = f"general_content:manual:{item.content_id}:{uuid4().hex}"
    else:
        idempotency_key = scheduled_idempotency_key(planned.planned_at.date(), item.slot, item.content_type)

    delivery = await session.scalar(
        select(GeneralContentDelivery).where(GeneralContentDelivery.idempotency_key == idempotency_key)
    )
    if delivery and delivery.status in TERMINAL_STATUSES:
        return DeliveryOutcome(
            status=delivery.status,
            content_id=delivery.content_id,
            delivery_id=delivery.id,
            message_id=delivery.telegram_message_id,
        )

    if delivery is None:
        delivery = GeneralContentDelivery(
            idempotency_key=idempotency_key,
            content_id=item.content_id,
            content_type=item.content_type,
            slot=item.slot,
            chat_key=GENERAL_CHAT_KEY,
            planned_at=planned.planned_at,
            status="planned",
            is_manual=manual,
        )
        session.add(delivery)
        await session.flush()

    if not manual:
        late_status = _late_status(item, planned.planned_at, now)
        if late_status:
            delivery.status = late_status
            await session.commit()
            return DeliveryOutcome(late_status, item.content_id, delivery.id)

    chat_id = await _general_chat_id(session, settings)
    if chat_id is None:
        delivery.status = "failed"
        delivery.error_code = "general_chat_unbound"
        delivery.error_detail = None
        await session.commit()
        await _alert_delivery_failure(bot, settings, "general_chat_unbound", item.content_id)
        return DeliveryOutcome("failed", item.content_id, delivery.id)

    delivery.chat_id = chat_id
    delivery.status = "sending"
    await session.commit()

    message, attempts, error_code, transient = await _send_with_retry(
        bot, chat_id, planned.effective_text
    )
    delivery.attempts += attempts
    if message is not None:
        delivery.telegram_message_id = int(message.message_id)
        delivery.sent_at = now
        delivery.status = "sent"
        delivery.error_code = None
        delivery.error_detail = None
        await session.commit()
        return DeliveryOutcome("sent", item.content_id, delivery.id, int(message.message_id))

    delivery.status = "failed"
    delivery.error_code = error_code or "telegram_error"
    delivery.error_detail = "transient_exhausted" if transient else "permanent"
    await session.commit()
    await _alert_delivery_failure(bot, settings, delivery.error_code, item.content_id)
    return DeliveryOutcome("failed", item.content_id, delivery.id)


async def run_scheduled_slot(
    bot: Bot,
    settings: Settings,
    session_factory,
    slot: Slot,
    *,
    now: datetime | None = None,
) -> DeliveryOutcome:
    local_now = now or datetime.now(ZoneInfo(settings.timezone))
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=ZoneInfo(settings.timezone))
    else:
        local_now = local_now.astimezone(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        planned = await plan_content(
            session,
            local_now.date(),
            slot,
            timezone_name=settings.timezone,
        )
        if planned is None:
            return DeliveryOutcome("no_content", None)
        return await deliver_planned_content(
            bot,
            settings,
            session,
            planned,
            now=local_now,
        )


async def list_overrides(session: AsyncSession) -> dict[str, GeneralContentOverride]:
    rows = (await session.scalars(select(GeneralContentOverride))).all()
    return {row.content_id: row for row in rows}


async def save_item_override(
    session: AsyncSession,
    content_id: str,
    *,
    actor_id: int | None,
    text: str | None = None,
    is_enabled: bool | None = None,
    is_skipped: bool | None = None,
) -> GeneralContentOverride:
    if static_item_by_id(content_id) is None:
        raise LookupError("content_not_found")
    row = await session.scalar(
        select(GeneralContentOverride).where(GeneralContentOverride.content_id == content_id)
    )
    if row is None:
        row = GeneralContentOverride(content_id=content_id, updated_by=actor_id)
        session.add(row)
    if text is not None:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text_required")
        row.override_text = cleaned
    if is_enabled is not None:
        row.is_enabled = is_enabled
    if is_skipped is not None:
        row.is_skipped = is_skipped
    row.updated_by = actor_id
    await session.commit()
    await session.refresh(row)
    return row


async def create_custom_holiday(
    session: AsyncSession,
    *,
    date_key: str,
    title: str,
    text: str,
    actor_id: int | None,
) -> GeneralCustomContent:
    # Accept either recurring MM-DD or one exact YYYY-MM-DD editorial date.
    try:
        if len(date_key) == 5:
            datetime.strptime(date_key, "%m-%d")
        else:
            date.fromisoformat(date_key)
    except ValueError as exc:
        raise ValueError("invalid_date") from exc
    if not text.strip():
        raise ValueError("text_required")
    row = GeneralCustomContent(
        content_id=f"holiday-custom-{uuid4().hex[:16]}",
        content_type="holiday",
        date_key=date_key,
        slot="morning",
        title=title.strip() or "Особая дата",
        text=text.strip(),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_custom_content(
    session: AsyncSession,
    content_id: str,
    *,
    actor_id: int | None,
    text: str | None = None,
    is_enabled: bool | None = None,
    title: str | None = None,
) -> GeneralCustomContent:
    row = await session.scalar(
        select(GeneralCustomContent).where(GeneralCustomContent.content_id == content_id)
    )
    if row is None:
        raise LookupError("content_not_found")
    if text is not None:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text_required")
        row.text = cleaned
    if is_enabled is not None:
        row.is_enabled = is_enabled
    if title is not None:
        row.title = title.strip() or row.title
    row.updated_by = actor_id
    await session.commit()
    await session.refresh(row)
    return row


async def content_item_by_id(session: AsyncSession, content_id: str) -> ContentItem | None:
    static = static_item_by_id(content_id)
    if static:
        resolution = await _override_resolution(session, static)
        return resolution.item
    row = await session.scalar(
        select(GeneralCustomContent).where(GeneralCustomContent.content_id == content_id)
    )
    if row is None or not row.is_enabled:
        return None
    return ContentItem(
        content_id=row.content_id,
        content_type=row.content_type,  # type: ignore[arg-type]
        slot=row.slot,  # type: ignore[arg-type]
        text=row.text,
        title=row.title,
        date_key=row.date_key,
        source="custom",
    )


async def send_item_now(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    content_id: str,
) -> DeliveryOutcome:
    item = await content_item_by_id(session, content_id)
    if item is None:
        raise LookupError("content_not_found")
    now = datetime.now(ZoneInfo(settings.timezone))
    planned = PlannedContent(item=item, planned_at=now, effective_text=item.text)
    return await deliver_planned_content(
        bot,
        settings,
        session,
        planned,
        now=now,
        manual=True,
    )


async def calendar_items(
    session: AsyncSession,
    *,
    start: date,
    days: int,
    timezone_name: str,
) -> list[dict[str, Any]]:
    days = max(1, min(days, 90))
    deliveries = (
        await session.scalars(
            select(GeneralContentDelivery)
            .where(
                GeneralContentDelivery.planned_at >= datetime.combine(start, time.min, tzinfo=ZoneInfo(timezone_name)),
                GeneralContentDelivery.planned_at < datetime.combine(start + timedelta(days=days), time.min, tzinfo=ZoneInfo(timezone_name)),
            )
            .order_by(GeneralContentDelivery.planned_at.asc())
        )
    ).all()
    delivery_map = {
        (row.planned_at.astimezone(ZoneInfo(timezone_name)).date(), row.slot): row
        for row in deliveries
        if not row.is_manual
    }
    result: list[dict[str, Any]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for slot in ("morning", "evening"):
            planned = await plan_content(
                session,
                day,
                slot,  # type: ignore[arg-type]
                timezone_name=timezone_name,
            )
            delivery = delivery_map.get((day, slot))
            result.append(
                {
                    "date": day.isoformat(),
                    "slot": slot,
                    "planned": planned.as_dict() if planned else None,
                    "status": delivery.status if delivery else ("planned" if planned else "disabled"),
                    "delivery_id": delivery.id if delivery else None,
                    "message_id": delivery.telegram_message_id if delivery else None,
                    "error_code": delivery.error_code if delivery else None,
                }
            )
    return result


async def delivery_history(session: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(GeneralContentDelivery)
            .order_by(GeneralContentDelivery.created_at.desc())
            .limit(max(1, min(limit, 300)))
        )
    ).all()
    return [
        {
            "id": row.id,
            "content_id": row.content_id,
            "content_type": row.content_type,
            "slot": row.slot,
            "status": row.status,
            "planned_at": row.planned_at.isoformat(),
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "attempts": row.attempts,
            "error_code": row.error_code,
            "is_manual": row.is_manual,
        }
        for row in rows
    ]


async def custom_holidays(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(GeneralCustomContent)
            .where(GeneralCustomContent.content_type == "holiday")
            .order_by(GeneralCustomContent.date_key.asc())
        )
    ).all()
    return [
        {
            "content_id": row.content_id,
            "date_key": row.date_key,
            "title": row.title,
            "text": row.text,
            "is_enabled": row.is_enabled,
        }
        for row in rows
    ]
