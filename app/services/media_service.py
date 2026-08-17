from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InputPollOption
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.content.era_public_pack import load_era_public_pack
from app.database.media_models import (
    MediaChannelDelivery,
    MediaChatNotice,
    MediaContentItem,
    MediaContentTask,
    MediaLibraryItem,
    MediaRequest,
)
from app.database.models import AppSetting, Direction, Event, Project, Task, User
from app.services.authorization_service import is_full_admin
from app.services.chat_registry_service import check_chats_health
from app.utils.constants import ApplicationStatus, TaskStatus

MEDIA_SETTINGS_KEY = "media_os_settings"
MEDIA_TASK_POINTS = {
    "text": 50,
    "stories": 50,
    "design": 100,
    "photo": 100,
    "video": 150,
    "editing": 200,
}
MEDIA_TASK_KINDS = {
    "text": "Текст",
    "design": "Дизайн",
    "photo": "Фото",
    "video": "Видео",
    "editing": "Монтаж",
    "stories": "Stories",
}
MEDIA_PACKAGES: dict[str, tuple[str, ...]] = {
    "announcement": ("text", "design"),
    "photo": ("photo",),
    "video": ("video",),
    "reels": ("video", "editing"),
    "full": ("text", "design", "photo", "video", "editing", "stories"),
}
WEEKDAY_OFFSET = {"ПН": 0, "СР": 2, "ПТ": 4, "ВС": 6}

DEFAULT_MEDIA_CONFIG: dict[str, Any] = {
    "auto_enabled": False,
    "paused_indefinitely": False,
    "paused_until": None,
}

LIBRARY_DEFAULTS = (
    (
        "chat",
        "Media Chat ЭРА",
        "Рабочий чат: задачи, координация и материалы.",
        "{media_chat_url}",
        10,
    ),
    (
        "channel",
        "Канал ЭРА",
        "Публичный канал, для которого работает контент-план.",
        "{era_channel_url}",
        20,
    ),
    (
        "template",
        "Canva — ЭРА",
        "Основной шаблон визуалов ЭРА.",
        "https://www.canva.com/design/DAGzsxPzP4E/5DAxg1OmRG6N3qQbr72pVA/edit?utm_content=DAGzsxPzP4E&utm_campaign=designshare&utm_medium=link2&utm_source=sharebutton",
        30,
    ),
    (
        "template",
        "Canva — КСООРС",
        "Шаблон для совместных публикаций КСООРС Армении.",
        "https://www.canva.com/design/DAG5K-l4SiI/dmKQtE-RMpDceNBq95_rqw/edit?utm_content=DAG5K-l4SiI&utm_campaign=designshare&utm_medium=link2&utm_source=sharebutton",
        40,
    ),
)


@dataclass(frozen=True)
class MediaAnalytics:
    planned: int
    published: int
    failed: int
    on_time_rate: float | None
    tasks_created: int
    tasks_completed: int


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    code: str
    message_id: int | None = None


def can_use_media_hub(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def can_manage_media(
    session: AsyncSession, user: User | None, settings: Settings
) -> bool:
    if user is None:
        return False
    if is_full_admin(user, settings, user.telegram_id):
        return True
    if user.is_blocked or user.is_archived:
        return False
    if user.telegram_id in settings.media_manager_ids:
        return True
    lead = await session.scalar(
        select(Direction.id).where(
            Direction.name == "Медиа",
            Direction.leader_id == user.id,
        )
    )
    return lead is not None


async def media_config(session: AsyncSession) -> dict[str, Any]:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == MEDIA_SETTINGS_KEY))
    stored = row.value if row and isinstance(row.value, dict) else {}
    return {**DEFAULT_MEDIA_CONFIG, **stored}


async def _save_media_config(session: AsyncSession, config: dict[str, Any]) -> dict[str, Any]:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == MEDIA_SETTINGS_KEY))
    if row is None:
        row = AppSetting(key=MEDIA_SETTINGS_KEY, value=config)
        session.add(row)
    else:
        row.value = config
    await session.flush()
    return config


def _pause_active(config: dict[str, Any], now: datetime) -> bool:
    if config.get("paused_indefinitely"):
        return True
    raw = config.get("paused_until")
    if not raw:
        return False
    try:
        until = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until > now


async def set_auto_enabled(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    *,
    enabled: bool,
) -> dict[str, Any]:
    config = await media_config(session)
    if enabled:
        health = await check_chats_health(bot, settings)
        channel = next((item for item in health if item.chat_key == "era_channel"), None)
        if channel is None or not channel.ok:
            raise ValueError("channel_not_ready")
    config["auto_enabled"] = bool(enabled)
    await _save_media_config(session, config)
    return config


async def pause_publication(
    session: AsyncSession,
    *,
    until: datetime | None = None,
    indefinitely: bool = False,
) -> dict[str, Any]:
    config = await media_config(session)
    config["paused_indefinitely"] = bool(indefinitely)
    config["paused_until"] = until.astimezone(timezone.utc).isoformat() if until else None
    return await _save_media_config(session, config)


async def resume_publication(session: AsyncSession) -> dict[str, Any]:
    config = await media_config(session)
    config["paused_indefinitely"] = False
    config["paused_until"] = None
    return await _save_media_config(session, config)


def _scheduled_at(
    start_date: date,
    week: int,
    weekday: str,
    clock: str,
    timezone_name: str,
) -> datetime:
    hour, minute = (int(part) for part in clock.split(":", 1))
    local_date = start_date + timedelta(days=(week - 1) * 7 + WEEKDAY_OFFSET[weekday])
    local = datetime.combine(local_date, time(hour=hour, minute=minute), ZoneInfo(timezone_name))
    return local.astimezone(timezone.utc)


async def seed_media_os(session: AsyncSession, settings: Settings) -> None:
    """Seed the approved authored pack and permanent Media library idempotently."""
    pack = load_era_public_pack()
    start = date.fromisoformat(pack["start_date"])
    for item in pack["items"]:
        source_key = f"era-public:w{int(item['week']):02d}:{item['weekday']}"
        exists = await session.scalar(
            select(MediaContentItem.id).where(MediaContentItem.source_key == source_key)
        )
        if exists:
            continue
        session.add(
            MediaContentItem(
                source_kind="authored_pack",
                source_key=source_key,
                week=int(item["week"]),
                theme=item.get("theme"),
                rubric=item.get("rubric"),
                kind=item.get("kind") or "text",
                body=item.get("body"),
                poll_question=item.get("poll_question"),
                poll_options=list(item.get("poll_options") or []),
                scheduled_at=_scheduled_at(
                    start,
                    int(item["week"]),
                    item["weekday"],
                    item["default_time"],
                    settings.timezone,
                ),
                status="scheduled",
                metadata_json={"weekday": item["weekday"], "approved": True},
            )
        )

    format_values = {
        "media_chat_url": settings.media_chat_url,
        "era_channel_url": settings.era_channel_url,
    }
    for kind, title, description, url_template, sort_order in LIBRARY_DEFAULTS:
        exists = await session.scalar(
            select(MediaLibraryItem.id).where(MediaLibraryItem.title == title)
        )
        if exists:
            continue
        session.add(
            MediaLibraryItem(
                kind=kind,
                title=title,
                description=description,
                url=url_template.format(**format_values),
                sort_order=sort_order,
                is_active=True,
            )
        )
    await session.flush()


async def list_library(session: AsyncSession) -> list[MediaLibraryItem]:
    return list(
        (
            await session.scalars(
                select(MediaLibraryItem)
                .where(MediaLibraryItem.is_active.is_(True))
                .order_by(MediaLibraryItem.sort_order, MediaLibraryItem.id)
            )
        ).all()
    )


async def list_content(
    session: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    limit: int = 250,
) -> list[MediaContentItem]:
    stmt = select(MediaContentItem)
    if date_from is not None:
        stmt = stmt.where(MediaContentItem.scheduled_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(MediaContentItem.scheduled_at < date_to)
    if status:
        stmt = stmt.where(MediaContentItem.status == status)
    stmt = stmt.order_by(MediaContentItem.scheduled_at, MediaContentItem.id).limit(limit)
    return list((await session.scalars(stmt)).all())


async def today_content(
    session: AsyncSession, settings: Settings, *, now: datetime | None = None
) -> list[MediaContentItem]:
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(settings.timezone))
    local_start = datetime.combine(local_now.date(), time.min, ZoneInfo(settings.timezone))
    start = local_start.astimezone(timezone.utc)
    end = (local_start + timedelta(days=1)).astimezone(timezone.utc)
    return await list_content(session, date_from=start, date_to=end)


async def create_content(
    session: AsyncSession,
    *,
    creator_id: int,
    body: str | None,
    kind: Literal["text", "poll"] = "text",
    scheduled_at: datetime | None = None,
    rubric: str | None = None,
    poll_question: str | None = None,
    poll_options: list[str] | None = None,
    source_kind: str = "manual",
    source_type: str | None = None,
    source_id: int | None = None,
) -> MediaContentItem:
    now_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    item = MediaContentItem(
        source_kind=source_kind,
        source_key=f"{source_kind}:{creator_id}:{now_key}",
        source_type=source_type,
        source_id=source_id,
        rubric=rubric,
        kind=kind,
        body=body.strip() if body else None,
        poll_question=poll_question.strip() if poll_question else None,
        poll_options=[option.strip() for option in (poll_options or []) if option.strip()],
        scheduled_at=scheduled_at,
        status="scheduled" if scheduled_at else "draft",
        created_by=creator_id,
        metadata_json={},
    )
    session.add(item)
    await session.flush()
    return item


async def create_idea(session: AsyncSession, user: User, text: str) -> MediaContentItem:
    idea = await create_content(
        session,
        creator_id=user.id,
        body=text,
        source_kind="idea",
    )
    idea.status = "idea"
    return idea


async def reschedule_content(
    session: AsyncSession, item: MediaContentItem, scheduled_at: datetime
) -> MediaContentItem:
    if item.status == "published":
        raise ValueError("already_published")
    item.scheduled_at = scheduled_at.astimezone(timezone.utc)
    item.status = "scheduled"
    await session.flush()
    return item


async def skip_content(session: AsyncSession, item: MediaContentItem) -> MediaContentItem:
    if item.status == "published":
        raise ValueError("already_published")
    item.status = "skipped"
    await session.flush()
    return item


def _is_media_task(task: Task) -> bool:
    return bool((getattr(task, "reward_json", None) or {}).get("media_task"))


async def create_content_tasks(
    session: AsyncSession,
    item: MediaContentItem,
    *,
    creator_id: int,
    task_kinds: tuple[str, ...] | list[str],
) -> list[MediaContentTask]:
    links: list[MediaContentTask] = []
    deadline = item.scheduled_at or (datetime.now(timezone.utc) + timedelta(days=7))
    # Give the team a buffer before publication whenever the item is still in
    # the future, but never create a deadline in the past.
    deadline = max(datetime.now(timezone.utc) + timedelta(hours=4), deadline - timedelta(hours=24))
    for task_kind in task_kinds:
        if task_kind not in MEDIA_TASK_KINDS:
            raise ValueError("invalid_media_task_kind")
        existing = await session.scalar(
            select(MediaContentTask).where(
                MediaContentTask.content_id == item.id,
                MediaContentTask.task_kind == task_kind,
            )
        )
        if existing:
            links.append(existing)
            continue
        task = Task(
            title=f"Медиа · {MEDIA_TASK_KINDS[task_kind]} · {item.rubric or 'Контент'}",
            description=(
                "Подготовь материал для Media Desk ЭРА. Результат отправляется "
                "через стандартную сдачу задачи и после проверки учитывается в Медиа."
            ),
            creator_id=creator_id,
            deadline=deadline,
            points=MEDIA_TASK_POINTS[task_kind],
            status=TaskStatus.PUBLISHED,
            task_type="challenge",
            audience_filter_json={},
            reward_json={
                "media_task": True,
                "media_content_id": item.id,
                "media_task_kind": task_kind,
                "counts_toward": ["media"],
            },
            chat_url=None,
            max_participants=1,
        )
        session.add(task)
        await session.flush()
        link = MediaContentTask(content_id=item.id, task_id=task.id, task_kind=task_kind)
        session.add(link)
        await session.flush()
        links.append(link)
    return links


async def media_tasks_for_user(
    session: AsyncSession, user_id: int, *, mine: bool
) -> list[Task]:
    from app.database.models import TaskParticipant

    stmt = (
        select(Task)
        .join(MediaContentTask, MediaContentTask.task_id == Task.id)
        .where(Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]))
        .order_by(Task.deadline, Task.id)
    )
    if mine:
        stmt = stmt.join(TaskParticipant, TaskParticipant.task_id == Task.id).where(
            TaskParticipant.user_id == user_id,
            TaskParticipant.status.in_(["pending", "accepted", "joined"]),
        )
    return list((await session.scalars(stmt)).unique().all())


async def request_media_package(
    session: AsyncSession,
    *,
    source_type: Literal["event", "project"],
    source_id: int,
    package_type: str,
    requester: User,
    settings: Settings,
) -> MediaRequest:
    if package_type not in MEDIA_PACKAGES:
        raise ValueError("invalid_package")
    existing = await session.scalar(
        select(MediaRequest).where(
            MediaRequest.source_type == source_type,
            MediaRequest.source_id == source_id,
            MediaRequest.package_type == package_type,
        )
    )
    if existing:
        return existing

    if source_type == "event":
        source = await session.get(Event, source_id)
        if source is None:
            raise ValueError("source_not_found")
        allowed = source.created_by == requester.id or await can_manage_media(session, requester, settings)
        source_title = source.title
        scheduled_at = None
        if source.event_date and source.event_time:
            local = datetime.combine(
                source.event_date, source.event_time, ZoneInfo(settings.timezone)
            )
            scheduled_at = local.astimezone(timezone.utc) - timedelta(days=3)
    else:
        source = await session.get(Project, source_id)
        if source is None:
            raise ValueError("source_not_found")
        allowed = source.author_id == requester.id or await can_manage_media(session, requester, settings)
        source_title = source.title
        scheduled_at = None
    if not allowed:
        raise PermissionError("forbidden")

    content = await create_content(
        session,
        creator_id=requester.id,
        body=f"Медиа-пакет для {source_type}: {source_title}",
        kind="text",
        scheduled_at=scheduled_at,
        rubric="Проекты ЭРА" if source_type == "project" else "События ЭРА",
        source_kind="request",
        source_type=source_type,
        source_id=source_id,
    )
    request = MediaRequest(
        source_type=source_type,
        source_id=source_id,
        package_type=package_type,
        requester_id=requester.id,
        content_id=content.id,
        status="open",
        metadata_json={"source_title": source_title},
    )
    session.add(request)
    await session.flush()
    await create_content_tasks(
        session,
        content,
        creator_id=requester.id,
        task_kinds=MEDIA_PACKAGES[package_type],
    )
    return request


def _channel_target(settings: Settings) -> int | str:
    raw = settings.era_channel_id
    if isinstance(raw, int):
        return raw
    text = str(raw or "").strip()
    if text.lstrip("-").isdigit():
        return int(text)
    if text:
        return text if text.startswith("@") else f"@{text}"
    if settings.era_channel_username:
        return f"@{settings.era_channel_username.lstrip('@')}"
    raise ValueError("channel_not_bound")


def _delivery_key(item: MediaContentItem) -> str:
    stamp = item.scheduled_at.isoformat() if item.scheduled_at else "unscheduled"
    return f"era-channel:{item.id}:{stamp}"


async def _send_content(bot: Bot, target: int | str, item: MediaContentItem):
    if item.kind == "poll":
        options = [InputPollOption(text=option) for option in (item.poll_options or [])]
        if not item.poll_question or len(options) < 2:
            raise ValueError("invalid_poll")
        return await bot.send_poll(
            chat_id=target,
            question=item.poll_question,
            options=options,
            is_anonymous=True,
        )
    if not item.body:
        raise ValueError("empty_content")
    return await bot.send_message(chat_id=target, text=item.body)


async def publish_content(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    item: MediaContentItem,
    *,
    manual: bool,
) -> PublishResult:
    """Publish exactly once unless a human explicitly retries a known-safe failure."""
    if item.status == "published":
        return PublishResult(False, "already_published", item.telegram_message_id)
    if not manual and item.source_kind != "authored_pack":
        return PublishResult(False, "auto_authored_only")

    key = _delivery_key(item)
    delivery = await session.scalar(
        select(MediaChannelDelivery).where(MediaChannelDelivery.delivery_key == key)
    )
    if delivery is not None:
        if delivery.status == "sent":
            return PublishResult(False, "already_published", delivery.telegram_message_id)
        if delivery.status in {"claimed", "uncertain"}:
            return PublishResult(False, "delivery_needs_review")
        if delivery.status == "failed_safe" and manual:
            delivery.status = "claimed"
            delivery.claimed_at = datetime.now(timezone.utc)
            delivery.last_error = None
            await session.commit()
        else:
            return PublishResult(False, "delivery_not_retryable")
    else:
        delivery = MediaChannelDelivery(
            content_id=item.id,
            delivery_key=key,
            status="claimed",
            attempt_count=0,
            claimed_at=datetime.now(timezone.utc),
        )
        session.add(delivery)
        # Durable claim before the Telegram side effect is the core duplicate
        # protection: a process crash can leave `claimed`, but never a second
        # blind AUTO send on restart.
        await session.commit()

    target = _channel_target(settings)
    message = None
    for attempt in range(1, 4):
        delivery.attempt_count = attempt
        try:
            message = await _send_content(bot, target, item)
            break
        except TelegramRetryAfter as exc:
            if attempt >= 3:
                delivery.status = "failed_safe"
                delivery.last_error = "telegram_retry_after_exhausted"
                await session.commit()
                return PublishResult(False, "retry_exhausted")
            await asyncio.sleep(min(max(float(exc.retry_after), 0.0), 30.0))
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            delivery.status = "failed_safe"
            delivery.last_error = type(exc).__name__
            await session.commit()
            return PublishResult(False, "telegram_rejected")
        except TelegramAPIError as exc:
            # API errors don't prove a successful send. Treat them as
            # uncertain rather than retrying into a possible duplicate.
            delivery.status = "uncertain"
            delivery.last_error = type(exc).__name__
            await session.commit()
            return PublishResult(False, "delivery_uncertain")
        except Exception as exc:  # network/runtime ambiguity: never blind retry
            delivery.status = "uncertain"
            delivery.last_error = type(exc).__name__
            await session.commit()
            return PublishResult(False, "delivery_uncertain")

    if message is None:
        delivery.status = "uncertain"
        delivery.last_error = "no_message_result"
        await session.commit()
        return PublishResult(False, "delivery_uncertain")

    now = datetime.now(timezone.utc)
    message_id = int(message.message_id)
    delivery.status = "sent"
    delivery.sent_at = now
    delivery.telegram_message_id = message_id
    delivery.last_error = None
    item.status = "published"
    item.published_at = now
    item.telegram_message_id = message_id
    await session.commit()
    return PublishResult(True, "published", message_id)


async def publish_due_channel_content(
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        config = await media_config(session)
        if not config.get("auto_enabled") or _pause_active(config, now):
            return
        due = list(
            (
                await session.scalars(
                    select(MediaContentItem)
                    .where(
                        MediaContentItem.source_kind == "authored_pack",
                        MediaContentItem.status == "scheduled",
                        MediaContentItem.scheduled_at.is_not(None),
                        MediaContentItem.scheduled_at <= now,
                    )
                    .order_by(MediaContentItem.scheduled_at, MediaContentItem.id)
                    .limit(10)
                )
            ).all()
        )
        for item in due:
            await publish_content(session, bot, settings, item, manual=False)


async def _send_media_chat_notice(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    *,
    notice_key: str,
    notice_kind: str,
    ref_type: str,
    ref_id: int,
    text: str,
) -> bool:
    if settings.media_chat_id is None:
        return False
    exists = await session.scalar(
        select(MediaChatNotice.id).where(MediaChatNotice.notice_key == notice_key)
    )
    if exists:
        return False
    try:
        message = await bot.send_message(settings.media_chat_id, text)
    except TelegramAPIError:
        return False
    session.add(
        MediaChatNotice(
            notice_key=notice_key,
            notice_kind=notice_kind,
            ref_type=ref_type,
            ref_id=ref_id,
            telegram_message_id=int(message.message_id),
            sent_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    return True


async def process_media_chat_automation(
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reason-based Media Chat automation: weekly plan + missing-work reminders."""
    if settings.media_chat_id is None:
        return
    now = datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        if local.weekday() == 0 and local.hour >= 9:
            week_start = datetime.combine(local.date(), time.min, ZoneInfo(settings.timezone))
            week_end = week_start + timedelta(days=7)
            items = await list_content(
                session,
                date_from=week_start.astimezone(timezone.utc),
                date_to=week_end.astimezone(timezone.utc),
            )
            if items:
                lines = ["Медиа ЭРА · план недели", ""]
                for item in items:
                    when = item.scheduled_at.astimezone(ZoneInfo(settings.timezone)) if item.scheduled_at else None
                    lines.append(
                        f"• {when.strftime('%a %H:%M') if when else 'без даты'} — {item.rubric or item.theme or 'Контент'}"
                    )
                iso = local.date().isocalendar()
                await _send_media_chat_notice(
                    session,
                    bot,
                    settings,
                    notice_key=f"weekly-plan:{iso.year}:{iso.week}",
                    notice_kind="weekly_plan",
                    ref_type="week",
                    ref_id=iso.week,
                    text="\n".join(lines),
                )

        deadline_to = now + timedelta(hours=24)
        rows = (
            await session.execute(
                select(Task, MediaContentTask)
                .join(MediaContentTask, MediaContentTask.task_id == Task.id)
                .where(
                    Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS]),
                    Task.deadline > now,
                    Task.deadline <= deadline_to,
                )
                .order_by(Task.deadline)
            )
        ).all()
        for task, link in rows:
            await _send_media_chat_notice(
                session,
                bot,
                settings,
                notice_key=f"task-24h:{task.id}:{task.deadline.isoformat()}",
                notice_kind="deadline_24h",
                ref_type="task",
                ref_id=task.id,
                text=(
                    f"До дедлайна медиа-задачи меньше 24 часов\n\n"
                    f"{task.title}\n"
                    f"Нужен результат до {task.deadline.astimezone(ZoneInfo(settings.timezone)).strftime('%d.%m %H:%M')}."
                ),
            )


async def analytics(session: AsyncSession) -> MediaAnalytics:
    planned = int(
        await session.scalar(
            select(func.count()).select_from(MediaContentItem).where(
                MediaContentItem.status.in_(["scheduled", "published", "skipped"])
            )
        )
        or 0
    )
    published = int(
        await session.scalar(
            select(func.count()).select_from(MediaContentItem).where(
                MediaContentItem.status == "published"
            )
        )
        or 0
    )
    failed = int(
        await session.scalar(
            select(func.count()).select_from(MediaChannelDelivery).where(
                MediaChannelDelivery.status.in_(["failed_safe", "uncertain"])
            )
        )
        or 0
    )
    published_rows = list(
        (
            await session.scalars(
                select(MediaContentItem).where(MediaContentItem.status == "published")
            )
        ).all()
    )
    scheduled_published = [
        item for item in published_rows if item.scheduled_at is not None and item.published_at is not None
    ]
    on_time = sum(
        1
        for item in scheduled_published
        if item.published_at <= item.scheduled_at + timedelta(minutes=15)
    )
    on_time_rate = (
        round(on_time / len(scheduled_published) * 100.0, 1)
        if scheduled_published
        else None
    )
    tasks_created = int(
        await session.scalar(select(func.count()).select_from(MediaContentTask)) or 0
    )
    tasks_completed = int(
        await session.scalar(
            select(func.count())
            .select_from(MediaContentTask)
            .join(Task, Task.id == MediaContentTask.task_id)
            .where(Task.status == TaskStatus.COMPLETED)
        )
        or 0
    )
    return MediaAnalytics(
        planned=planned,
        published=published,
        failed=failed,
        on_time_rate=on_time_rate,
        tasks_created=tasks_created,
        tasks_completed=tasks_completed,
    )
