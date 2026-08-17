from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services.media_attachment_service import (
    confirm_attachment,
    create_pending_task_attachment,
    discard_attachment,
    task_id_for_replied_card,
)
from app.utils.constants import ApplicationStatus

router = Router(name="media_chat_files")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _confirmation_keyboard(attachment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Прикрепить",
                    callback_data=f"media:attach:{attachment_id}",
                ),
                InlineKeyboardButton(
                    text="Не прикреплять",
                    callback_data=f"media:drop:{attachment_id}",
                ),
            ]
        ]
    )


def _file_payload(message: Message) -> tuple[str, str, str | None, str | None, str | None] | None:
    if message.document:
        return (
            "document",
            message.document.file_id,
            message.document.file_unique_id,
            message.document.file_name,
            message.document.mime_type,
        )
    if message.video:
        return (
            "video",
            message.video.file_id,
            message.video.file_unique_id,
            message.video.file_name,
            message.video.mime_type,
        )
    if message.photo:
        photo = message.photo[-1]
        return ("photo", photo.file_id, photo.file_unique_id, None, "image/jpeg")
    return None


@router.message(F.document | F.video | F.photo)
async def media_chat_file_reply(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    # Files elsewhere (including arbitrary files in Media Chat) are untouched.
    if settings.media_chat_id is None or message.chat.id != settings.media_chat_id:
        return
    if not _approved(user) or message.reply_to_message is None:
        return

    task_id = await task_id_for_replied_card(
        session, telegram_message_id=message.reply_to_message.message_id
    )
    if task_id is None:
        return
    payload = _file_payload(message)
    if payload is None:
        return
    media_type, file_id, unique_id, filename, mime_type = payload
    try:
        attachment = await create_pending_task_attachment(
            session,
            task_id=task_id,
            user=user,
            media_type=media_type,
            telegram_file_id=file_id,
            telegram_file_unique_id=unique_id,
            filename=filename,
            mime_type=mime_type,
            source_chat_id=message.chat.id,
            source_message_id=message.message_id,
        )
        await session.commit()
    except PermissionError:
        await message.reply(
            "Сначала возьмите эту медиа-задачу в Mini App. "
            "Файл не был прикреплён."
        )
        return
    except ValueError:
        return

    if attachment.status == "attached":
        await message.reply("Этот файл уже прикреплён к задаче ✓")
        return
    await message.reply(
        f"Прикрепить файл к задаче #{task_id}?",
        reply_markup=_confirmation_keyboard(attachment.id),
    )


@router.callback_query(F.data.startswith("media:attach:"))
async def media_confirm_attachment(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
) -> None:
    if not _approved(user) or call.data is None:
        await call.answer("Недоступно", show_alert=True)
        return
    try:
        attachment_id = int(call.data.rsplit(":", 1)[1])
        attachment = await confirm_attachment(
            session, attachment_id=attachment_id, user=user
        )
        await session.commit()
    except (ValueError, PermissionError):
        await call.answer("Не удалось прикрепить этот файл", show_alert=True)
        return
    if call.message:
        await call.message.edit_text(
            f"Файл прикреплён к задаче #{attachment.target_id} ✓"
        )
    await call.answer("Прикреплено")


@router.callback_query(F.data.startswith("media:drop:"))
async def media_discard_attachment(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
) -> None:
    if not _approved(user) or call.data is None:
        await call.answer("Недоступно", show_alert=True)
        return
    try:
        attachment_id = int(call.data.rsplit(":", 1)[1])
        await discard_attachment(session, attachment_id=attachment_id, user=user)
        await session.commit()
    except (ValueError, PermissionError):
        await call.answer("Не удалось отменить", show_alert=True)
        return
    if call.message:
        await call.message.edit_text("Файл не прикреплён.")
    await call.answer("Отменено")
