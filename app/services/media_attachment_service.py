from __future__ import annotations

from datetime import datetime, timezone
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.media_models import MediaAttachment, MediaChatNotice, MediaContentTask
from app.database.models import Task, User
from app.services import task_service
from app.utils.constants import TaskStatus

logger = logging.getLogger(__name__)


async def create_pending_task_attachment(
    session: AsyncSession,
    *,
    task_id: int,
    user: User,
    media_type: str,
    telegram_file_id: str,
    telegram_file_unique_id: str | None,
    filename: str | None,
    mime_type: str | None,
    source_chat_id: int,
    source_message_id: int,
) -> MediaAttachment:
    """Stage a reply file without attaching it to the task yet."""
    task = await session.get(Task, task_id)
    if task is None or not await task_service.can_submit(session, task, user):
        raise PermissionError("task_not_owned")
    media_link = await session.scalar(
        select(MediaContentTask.id).where(MediaContentTask.task_id == task_id)
    )
    if media_link is None:
        raise ValueError("not_media_task")

    existing = await session.scalar(
        select(MediaAttachment).where(
            MediaAttachment.source_chat_id == source_chat_id,
            MediaAttachment.source_message_id == source_message_id,
            MediaAttachment.uploader_id == user.id,
        )
    )
    if existing is not None:
        return existing

    attachment = MediaAttachment(
        target_type="task",
        target_id=task_id,
        uploader_id=user.id,
        status="pending",
        media_type=media_type,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        filename=filename,
        mime_type=mime_type,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def confirm_attachment(
    session: AsyncSession, *, attachment_id: int, user: User
) -> MediaAttachment:
    attachment = await session.get(MediaAttachment, attachment_id)
    if attachment is None:
        raise ValueError("attachment_not_found")
    if attachment.uploader_id != user.id:
        raise PermissionError("attachment_owner_required")
    task = await session.get(Task, attachment.target_id)
    if task is None or not await task_service.can_submit(session, task, user):
        raise PermissionError("task_not_owned")
    if attachment.status == "attached":
        return attachment
    if attachment.status != "pending":
        raise ValueError("attachment_not_pending")
    attachment.status = "attached"
    attachment.confirmed_at = datetime.now(timezone.utc)
    await session.flush()
    return attachment


async def discard_attachment(
    session: AsyncSession, *, attachment_id: int, user: User
) -> MediaAttachment:
    attachment = await session.get(MediaAttachment, attachment_id)
    if attachment is None:
        raise ValueError("attachment_not_found")
    if attachment.uploader_id != user.id:
        raise PermissionError("attachment_owner_required")
    if attachment.status == "attached":
        raise ValueError("attachment_already_attached")
    attachment.status = "discarded"
    await session.flush()
    return attachment


async def attached_files(
    session: AsyncSession, *, target_type: str, target_id: int
) -> list[MediaAttachment]:
    return list(
        (
            await session.scalars(
                select(MediaAttachment)
                .where(
                    MediaAttachment.target_type == target_type,
                    MediaAttachment.target_id == target_id,
                    MediaAttachment.status == "attached",
                )
                .order_by(MediaAttachment.confirmed_at, MediaAttachment.id)
            )
        ).all()
    )


async def task_id_for_replied_card(
    session: AsyncSession, *, telegram_message_id: int
) -> int | None:
    return await session.scalar(
        select(MediaChatNotice.ref_id).where(
            MediaChatNotice.notice_kind == "task_card",
            MediaChatNotice.ref_type == "task",
            MediaChatNotice.telegram_message_id == telegram_message_id,
        )
    )


TELEGRAM_MESSAGE_MAX_UTF16_UNITS = 4096
MEDIA_TASK_CARD_TRUNCATED = "\n… (текст сокращён, полное описание — в Mini App)"


def _utf16_units(value: str) -> int:
    # Emoji can occupy two UTF-16 units. Count both so the Telegram limit
    # cannot be exceeded by an emoji-heavy task description.
    return len(value.encode("utf-16-le")) // 2


def _media_task_card_text(task: Task) -> str:
    header = "🎬 Медиа-задача\n\n"
    deadline = (
        task.deadline.astimezone(timezone.utc).strftime("%d.%m %H:%M")
        if task.deadline else "Без срока"
    )
    footer = (
        f"\n\nДедлайн: {deadline}\n"
        f"Баллы после проверки: +{task.points}\n\n"
        "Возьмите задачу в Mini App. Если отправляете файл сюда — "
        "ответьте именно на эту карточку. Бот отдельно спросит подтверждение."
    )
    body = f"{task.title or 'Без названия'}\n\n{task.description or 'Без описания'}"
    available = TELEGRAM_MESSAGE_MAX_UTF16_UNITS - _utf16_units(header + footer)
    if _utf16_units(body) > available:
        budget = available - _utf16_units(MEDIA_TASK_CARD_TRUNCATED)
        # Binary search by UTF-16 units for emoji-heavy descriptions.
        lo, hi = 0, len(body)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _utf16_units(body[:mid]) <= budget:
                lo = mid
            else:
                hi = mid - 1
        body = body[:lo].rstrip() + MEDIA_TASK_CARD_TRUNCATED
    return header + body + footer


async def post_missing_media_task_cards(
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Publish one card per Media task into Media Chat, idempotently."""
    if settings.media_chat_id is None:
        return
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Task, MediaContentTask)
                .join(MediaContentTask, MediaContentTask.task_id == Task.id)
                # Exclude already-claimed cards in SQL *before* LIMIT. If we
                # limit first, 100 old tasks with notices can permanently starve
                # every newer task, even though the worker runs each minute.
                .outerjoin(
                    MediaChatNotice,
                    MediaChatNotice.notice_key == (
                        "media-task-card:" + cast(Task.id, String)
                    ),
                )
                .where(
                    Task.status.in_(
                        [TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
                    ),
                    MediaChatNotice.id.is_(None),
                )
                .order_by(Task.created_at, Task.id)
                # Do not flood Media Chat when an old backlog is unblocked.
                # This scheduler runs every minute: release at most one card
                # per tick while still eventually reaching newer tasks.
                .limit(1)
            )
        ).all()
        for task, link in rows:
            notice_key = f"media-task-card:{task.id}"
            exists = await session.scalar(
                select(MediaChatNotice.id).where(MediaChatNotice.notice_key == notice_key)
            )
            if exists:
                continue
            text = _media_task_card_text(task)
            # Claim the unique notice key *before* Telegram I/O. A timeout
            # may mean Telegram published the card; retrying without a durable
            # claim can spam the chat or attach replies to the wrong card.
            # A NULL message ID means "delivery outcome needs review".
            notice = MediaChatNotice(
                notice_key=notice_key,
                notice_kind="task_card",
                ref_type="task",
                ref_id=task.id,
                telegram_message_id=None,
                sent_at=datetime.now(timezone.utc),
            )
            session.add(notice)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # Another worker may have claimed this same card. Do not send.
                if await session.scalar(
                    select(MediaChatNotice.id).where(MediaChatNotice.notice_key == notice_key)
                ) is not None:
                    continue
                raise
            try:
                message = await bot.send_message(settings.media_chat_id, text)
            except TelegramAPIError as exc:
                # Keep the claim even for network errors: the message might
                # already exist. An administrator must reconcile it manually.
                logger.warning(
                    "Media task card delivery needs review: %s (%s)",
                    notice_key, type(exc).__name__,
                )
                continue
            message_id = getattr(message, "message_id", None)
            if type(message_id) is not int or message_id <= 0:
                # Telegram may have delivered the card despite a bad response.
                logger.warning("Media task card response needs review: %s", notice_key)
                continue
            notice.telegram_message_id = message_id
            notice.sent_at = datetime.now(timezone.utc)
            await session.commit()
