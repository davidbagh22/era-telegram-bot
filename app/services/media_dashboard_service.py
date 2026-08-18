from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.media_models import MediaAttachment, MediaContentItem, MediaContentTask, MediaLibraryItem
from app.database.models import PointTransaction, Task, TaskParticipant, TaskSubmission, User
from app.utils.constants import TaskStatus

MEDIA_GUIDE = {
    "principles": [
        "Живо и коротко: без канцелярита и пресс-релизного ощущения.",
        "Одна публикация — одна главная мысль.",
        "Первый абзац должен удержать внимание, а не пересказать заголовок.",
        "Показываем движение, людей и реальную ценность участия в ЭРА.",
        "Не публикуем неподтверждённые цифры, имена, даты и внешние обещания.",
    ],
    "post": [
        "Hook — первая строка цепляет вопросом, конфликтом или сильной деталью.",
        "Context — быстро объясняем, что происходит.",
        "Value — что человек понял, получил или может сделать дальше.",
        "Final — короткое послевкусие без шаблонного призыва.",
    ],
    "reels": [
        "0–2 сек: визуальный или смысловой hook.",
        "2–8 сек: основная мысль без длинного вступления.",
        "8–15 сек: развитие и финальная точка.",
    ],
    "visual": [
        "Тёмная premium-среда ЭРА, сильная типографическая иерархия.",
        "Один главный визуальный акцент, минимум декоративного шума.",
        "Читаемость важнее эффекта: текст не должен теряться на фоне.",
    ],
}


@dataclass(frozen=True)
class MediaTodayAction:
    kind: str
    severity: str
    title: str
    detail: str
    content_id: int | None = None
    task_id: int | None = None


@dataclass(frozen=True)
class MediaTeamMember:
    user_id: int
    name: str
    materials_created: int
    tasks_completed: int
    deadline_rate: float | None
    published_contributions: int
    media_points: int


async def seed_media_guide(session: AsyncSession, settings: Settings) -> None:
    """Idempotent: inserts the Guide item if missing, and self-heals it to
    the current internal-route contract if an older seed already created it
    with a full external URL (DELTA ToR §32 -- fixing the "opens in Safari"
    bug must not require every environment to be re-seeded from scratch)."""
    title = "Гайд Media ЭРА"
    # No settings.effective_miniapp_url/host baked in -- this is a plain
    # in-app hash route, resolved relative to wherever the Mini App is
    # already running, and MUST be opened with SPA navigation, never
    # window.open/Telegram openLink (see MediaScreen's openLibraryItem).
    route = "media/guide"
    description = "Tone of voice, структура постов и Reels, правила визуала."
    existing = await session.scalar(select(MediaLibraryItem).where(MediaLibraryItem.title == title))
    if existing is not None:
        if existing.destination_type != "internal_route" or existing.url != route:
            existing.destination_type = "internal_route"
            existing.url = route
        return
    session.add(
        MediaLibraryItem(
            kind="guide",
            category="guides",
            title=title,
            description=description,
            url=route,
            destination_type="internal_route",
            sort_order=25,
            is_active=True,
        )
    )
    await session.flush()


async def actionable_today(
    session: AsyncSession, *, now: datetime | None = None
) -> list[MediaTodayAction]:
    now = now or datetime.now(timezone.utc)
    actions: list[MediaTodayAction] = []
    soon = list((await session.scalars(select(MediaContentItem).where(
        MediaContentItem.scheduled_at.is_not(None),
        MediaContentItem.scheduled_at >= now,
        MediaContentItem.scheduled_at <= now + timedelta(hours=2),
        func.lower(MediaContentItem.status).not_in(["published", "skipped"]),
    ).order_by(MediaContentItem.scheduled_at))).all())
    for item in soon:
        minutes = max(0, int((item.scheduled_at - now).total_seconds() // 60))
        actions.append(MediaTodayAction(
            kind="publication_soon",
            severity="high" if minutes <= 30 else "medium",
            title=item.title or item.rubric or item.theme or "Публикация ЭРА",
            detail=f"До публикации около {minutes} мин.",
            content_id=item.id,
        ))

    review_rows = (await session.execute(
        select(Task, TaskSubmission)
        .join(MediaContentTask, MediaContentTask.task_id == Task.id)
        .join(TaskSubmission, TaskSubmission.task_id == Task.id)
        .where(TaskSubmission.status == "pending")
        .order_by(TaskSubmission.created_at)
    )).all()
    for task, _submission in review_rows:
        actions.append(MediaTodayAction(
            kind="review_waiting", severity="medium", title=task.title,
            detail="Результат участника ждёт проверки Media Lead.", task_id=task.id,
        ))

    overdue = list((await session.scalars(
        select(Task).join(MediaContentTask, MediaContentTask.task_id == Task.id).where(
            Task.deadline < now,
            Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]),
        ).order_by(Task.deadline)
    )).unique().all())
    for task in overdue:
        actions.append(MediaTodayAction(
            kind="task_overdue", severity="high", title=task.title,
            detail="Дедлайн медиа-задачи уже прошёл.", task_id=task.id,
        ))

    upcoming = list((await session.scalars(select(MediaContentItem).where(
        MediaContentItem.scheduled_at.is_not(None),
        MediaContentItem.scheduled_at >= now,
        MediaContentItem.scheduled_at <= now + timedelta(days=2),
        (MediaContentItem.needs_visual.is_(True) | MediaContentItem.needs_video.is_(True)),
        func.lower(MediaContentItem.status).not_in(["published", "skipped"]),
    ).order_by(MediaContentItem.scheduled_at))).all())
    for item in upcoming:
        kinds = set((await session.scalars(
            select(MediaContentTask.task_kind).where(MediaContentTask.content_id == item.id)
        )).all())
        attached = int(await session.scalar(select(func.count(MediaAttachment.id)).where(
            MediaAttachment.target_type == "content",
            MediaAttachment.target_id == item.id,
            MediaAttachment.status == "attached",
        )) or 0)
        missing_visual = item.needs_visual and not (kinds & {"design", "photo"}) and not attached
        missing_video = item.needs_video and not (kinds & {"video", "editing"}) and not attached
        if missing_visual or missing_video:
            missing = "визуал и видео" if missing_visual and missing_video else "визуал" if missing_visual else "видео"
            actions.append(MediaTodayAction(
                kind="asset_missing", severity="medium",
                title=item.title or item.rubric or "Контент ЭРА",
                detail=f"Перед публикацией не подготовлены: {missing}.", content_id=item.id,
            ))
    return actions


async def average_cycle_time_hours(session: AsyncSession) -> float | None:
    rows = list((await session.scalars(
        select(MediaContentItem).where(MediaContentItem.published_at.is_not(None))
    )).all())
    values = [
        (item.published_at - item.created_at).total_seconds() / 3600
        for item in rows
        if item.published_at is not None and item.created_at is not None and item.published_at >= item.created_at
    ]
    return round(sum(values) / len(values), 1) if values else None


async def team_analytics(session: AsyncSession) -> list[MediaTeamMember]:
    media_task_ids = set((await session.scalars(select(MediaContentTask.task_id))).all())
    if not media_task_ids:
        return []
    participant_ids = set((await session.scalars(select(TaskParticipant.user_id).where(
        TaskParticipant.task_id.in_(media_task_ids),
        TaskParticipant.status.in_(["accepted", "joined"]),
    ))).all())
    approved_ids = set((await session.scalars(select(TaskSubmission.user_id).where(
        TaskSubmission.task_id.in_(media_task_ids), TaskSubmission.status == "approved",
    ))).all())
    members: list[MediaTeamMember] = []
    for user_id in sorted(participant_ids | approved_ids):
        user = await session.get(User, user_id)
        if user is None:
            continue
        approved = list((await session.scalars(select(TaskSubmission).where(
            TaskSubmission.user_id == user_id,
            TaskSubmission.task_id.in_(media_task_ids),
            TaskSubmission.status == "approved",
        ))).all())
        task_ids = {row.task_id for row in approved}
        deadlines_met = 0
        for row in approved:
            task = await session.get(Task, row.task_id)
            if task is not None and row.created_at <= task.deadline:
                deadlines_met += 1
        published = 0
        points = 0
        if task_ids:
            published = int(await session.scalar(
                select(func.count(func.distinct(MediaContentTask.content_id)))
                .select_from(MediaContentTask)
                .join(MediaContentItem, MediaContentItem.id == MediaContentTask.content_id)
                .where(MediaContentTask.task_id.in_(task_ids), func.lower(MediaContentItem.status) == "published")
            ) or 0)
            points = int(await session.scalar(select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == user_id,
                PointTransaction.related_task_id.in_(task_ids),
                PointTransaction.points > 0,
            )) or 0)
        name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
        members.append(MediaTeamMember(
            user_id=user.id,
            name=name or f"Участник #{user.id}",
            materials_created=len(approved),
            tasks_completed=len(task_ids),
            deadline_rate=round(deadlines_met / len(approved) * 100.0, 1) if approved else None,
            published_contributions=published,
            media_points=points,
        ))
    return members
