from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, User
from app.keyboards.common import back_keyboard
from app.services.event_registration_notice_service import (
    RegistrationNoticeKind,
    deliver_registration_notice,
    enqueue_registration_notice,
)
from app.services.event_registration_service import mark_not_coming
from app.services.event_service import promote_waitlist, send_committed_registration_notice
from app.utils import texts
from app.utils.constants import ApplicationStatus, RegistrationStatus

router = Router(name="event_plans_changed")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    return True


def _event_id_from_callback(data: str | None) -> int | None:
    """Accept only positive ASCII numeric IDs from our own callback namespace."""
    prefix = "event:plans_changed:"
    if not data or not data.startswith(prefix):
        return None
    raw_id = data[len(prefix):]
    if not raw_id or len(raw_id) > 10 or not raw_id.isascii() or not raw_id.isdecimal():
        return None
    event_id = int(raw_id)
    # Event.id is PostgreSQL INTEGER (signed 32-bit); reject oversized values
    # before asyncpg attempts to bind them and raises a database DataError.
    return event_id if 0 < event_id <= 2_147_483_647 else None


@router.callback_query(F.data.startswith("event:plans_changed:"))
async def plans_changed(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return

    event_id = _event_id_from_callback(call.data)
    if event_id is None:
        await call.message.answer(
            "Не удалось открыть регистрацию. Вернитесь в афишу.",
            reply_markup=back_keyboard("events:list"),
        )
        return
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user.id,
        )
    )
    event = await session.get(Event, event_id)

    if registration is None or event is None:
        await call.message.answer(
            "Регистрация на мероприятие не найдена.",
            reply_markup=back_keyboard("events:list"),
        )
        return

    was_waiting = registration.status == RegistrationStatus.WAITLIST
    if was_waiting:
        registration.status = RegistrationStatus.CANCELLED
        reply = (
            f"Вы покинули лист ожидания на «{event.title}».\n\n"
            "Если снова захотите участвовать и регистрация ещё открыта — вернитесь в афишу."
        )
        expected_status = RegistrationStatus.CANCELLED
    elif mark_not_coming(registration, event):
        reply = (
            f"Поняли. Отметили, что вы не сможете прийти на «{event.title}».\n\n"
            "Спасибо, что сообщили заранее — место сможет занять участник из листа ожидания."
        )
        expected_status = RegistrationStatus.NOT_COMING
    else:
        await call.message.answer(
            "Статус этой регистрации уже нельзя изменить через бот.",
            reply_markup=back_keyboard("events:list"),
        )
        return

    # Mirror Mini App cancel: free seat → promote oldest waiter after write, before commit.
    notice = None
    if not was_waiting:
        promoted = await promote_waitlist(session, event)
        if promoted is not None:
            promoted_user = await session.get(User, promoted.user_id)
            if promoted_user is not None:
                notice = await enqueue_registration_notice(
                    session,
                    promoted,
                    promoted_user.telegram_id,
                    RegistrationNoticeKind.PROMOTION,
                )

    await session.commit()
    if notice is not None:
        await deliver_registration_notice(session, notice, call.bot.send_message)
    await send_committed_registration_notice(
        session,
        registration.id,
        expected_status,
        lambda: call.message.answer(reply, reply_markup=back_keyboard("events:list")),
    )
