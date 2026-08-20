from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.media_models import (
    MediaChannelDelivery,
    MediaContentItem,
    MediaContentStatus,
    MediaContentTask,
)
from app.database.models import Task
from app.utils.constants import TaskStatus


TERMINAL_STATUSES = {
    MediaContentStatus.PUBLISHED.value,
    MediaContentStatus.SKIPPED.value,
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    MediaContentStatus.IDEA.value: {
        MediaContentStatus.PLANNED.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.PLANNED.value: {
        MediaContentStatus.ASSIGNED.value,
        MediaContentStatus.IN_PROGRESS.value,
        MediaContentStatus.REVIEW.value,
        MediaContentStatus.READY.value,
        MediaContentStatus.SCHEDULED.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.ASSIGNED.value: {
        MediaContentStatus.IN_PROGRESS.value,
        MediaContentStatus.REVIEW.value,
        MediaContentStatus.READY.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.IN_PROGRESS.value: {
        MediaContentStatus.REVIEW.value,
        MediaContentStatus.READY.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.REVIEW.value: {
        MediaContentStatus.IN_PROGRESS.value,
        MediaContentStatus.READY.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.READY.value: {
        MediaContentStatus.SCHEDULED.value,
        MediaContentStatus.PUBLISHED.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.SCHEDULED.value: {
        MediaContentStatus.READY.value,
        MediaContentStatus.PUBLISHED.value,
        MediaContentStatus.FAILED.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.FAILED.value: {
        MediaContentStatus.READY.value,
        MediaContentStatus.SCHEDULED.value,
        MediaContentStatus.SKIPPED.value,
    },
    MediaContentStatus.PUBLISHED.value: set(),
    MediaContentStatus.SKIPPED.value: set(),
}


def normalize_status(value: str | MediaContentStatus) -> str:
    raw = value.value if isinstance(value, MediaContentStatus) else str(value).strip().lower()
    if raw == "draft":
        return MediaContentStatus.PLANNED.value
    try:
        return MediaContentStatus(raw).value
    except ValueError as exc:
        raise ValueError(f"invalid_media_content_status:{raw}") from exc


def product_status(value: str | MediaContentStatus) -> str:
    """Return the exact MASTER status label used by API/UI documentation."""
    return MediaContentStatus(normalize_status(value)).name


def can_transition(current: str, target: str) -> bool:
    current_value = normalize_status(current)
    target_value = normalize_status(target)
    return current_value == target_value or target_value in ALLOWED_TRANSITIONS[current_value]


async def transition_content_status(
    session: AsyncSession,
    item: MediaContentItem,
    target: str | MediaContentStatus,
) -> MediaContentItem:
    current = normalize_status(item.status)
    target_value = normalize_status(target)
    if not can_transition(current, target_value):
        raise ValueError(f"invalid_media_transition:{current}->{target_value}")
    item.status = target_value
    await session.flush()
    return item


async def _linked_tasks(session: AsyncSession, content_id: int) -> list[Task]:
    return list(
        (
            await session.scalars(
                select(Task)
                .join(MediaContentTask, MediaContentTask.task_id == Task.id)
                .where(MediaContentTask.content_id == content_id)
                .order_by(Task.id)
            )
        ).all()
    )


async def _latest_delivery(
    session: AsyncSession, content_id: int
) -> MediaChannelDelivery | None:
    return await session.scalar(
        select(MediaChannelDelivery)
        .where(MediaChannelDelivery.content_id == content_id)
        .order_by(MediaChannelDelivery.id.desc())
        .limit(1)
    )


async def reconcile_content_state(
    session: AsyncSession,
    item: MediaContentItem,
) -> MediaContentItem:
    """Derive the pipeline state from the existing Task and delivery engines.

    No second task/review/scheduler engine is introduced. Media simply reflects
    what the canonical Task workflow and Telegram delivery ledger already know.
    """
    current = normalize_status(item.status)
    if current in TERMINAL_STATUSES:
        return item

    delivery = await _latest_delivery(session, item.id)
    if delivery is not None:
        if delivery.status == "sent":
            item.status = MediaContentStatus.PUBLISHED.value
            return item
        if delivery.status in {"failed_safe", "uncertain"}:
            item.status = MediaContentStatus.FAILED.value
            return item

    tasks = await _linked_tasks(session, item.id)
    if not tasks:
        if item.source_kind == "idea" and item.scheduled_at is None:
            target = MediaContentStatus.IDEA.value
        elif item.scheduled_at is not None:
            target = MediaContentStatus.SCHEDULED.value
        else:
            target = MediaContentStatus.PLANNED.value
        item.status = target
        return item

    task_statuses = {str(task.status).lower() for task in tasks}
    if TaskStatus.REVIEW.value in task_statuses:
        target = MediaContentStatus.REVIEW.value
    elif all(status == TaskStatus.COMPLETED.value for status in task_statuses):
        target = (
            MediaContentStatus.SCHEDULED.value
            if item.scheduled_at is not None
            else MediaContentStatus.READY.value
        )
    elif TaskStatus.IN_PROGRESS.value in task_statuses:
        target = MediaContentStatus.IN_PROGRESS.value
    else:
        target = MediaContentStatus.ASSIGNED.value
    item.status = target
    return item


async def reconcile_media_pipeline_job(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        items = list(
            (
                await session.scalars(
                    select(MediaContentItem)
                    .where(
                        MediaContentItem.status.notin_(
                            [
                                MediaContentStatus.PUBLISHED.value,
                                MediaContentStatus.SKIPPED.value,
                            ]
                        )
                    )
                    .order_by(MediaContentItem.id)
                    .limit(500)
                )
            ).all()
        )
        changed = False
        for item in items:
            before = normalize_status(item.status)
            await reconcile_content_state(session, item)
            changed = changed or normalize_status(item.status) != before
        if changed:
            await session.commit()
