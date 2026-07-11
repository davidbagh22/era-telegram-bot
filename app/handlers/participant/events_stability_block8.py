from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, User
from app.keyboards.participant import event_card_keyboard, event_list_keyboard
from app.services.event_card import send_event_card
from app.services.event_registration_service import registration_stats
from app.services.event_service import (
    PUBLIC_EVENT_STATUSES,
    REGISTRATION_ALLOWED_STATUSES,
    published_events,
    register_for_event,
)
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_events_stability_block8")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _send_event_list(message: Message, user: User | None, session: AsyncSession) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    events = await published_events(session)
    if not events:
        await message.answer(
            "📅 Афиша\n\nСейчас нет открытых мероприятий. Как только команда ЭРА опубликует новое событие, оно появится здесь"
        )
        return
    await message.answer(ux_texts.EVENTS_LIST_HEADER, reply_markup=event_list_keyboard(events))


@router.message(F.text.in_({"📅 Афиша", "📅 Мероприятия"}))
@router.message(Command("events"), F.chat.type == "private")
async def event_list_button(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.callback_query(F.data == "events:list")
async def event_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    await _send_event_list(call.message, user, session)


@router.callback_query(F.data.startswith("event:view:"))
async def event_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        await call.message.answer("Это мероприятие сейчас недоступно в афише")
        return
    stats = await registration_stats(session, event)
    can_register = (
        event.status in REGISTRATION_ALLOWED_STATUSES
        and (event.participant_limit is None or int(stats["free"]) > 0)
    )
    extra = None
    if event.status not in REGISTRATION_ALLOWED_STATUSES:
        extra = "Регистрация закрыта, но карточка мероприятия остаётся доступна."
    elif event.participant_limit is not None and int(stats["free"]) <= 0:
        extra = "Свободных мест сейчас нет."
    await send_event_card(
        call.message,
        event,
        available=str(stats["free"]),
        registered=int(stats["registered"]),
        extra_text=extra,
        keyboard=event_card_keyboard(event.id, can_register=can_register),
    )


@router.callback_query(F.data.startswith("event:join:"))
async def event_join(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        await call.message.answer("Это мероприятие сейчас недоступно")
        return
    _, error = await register_for_event(session, event, user.id)
    if error == "already":
        await call.message.answer(texts.EVENT_ALREADY_REGISTERED)
        return
    if error == "full":
        await call.message.answer(texts.EVENT_FULL)
        return
    if error == "closed":
        await call.message.answer("Регистрация на это мероприятие закрыта, но само событие остаётся в афише")
        return
    stats = await registration_stats(session, event)
    await call.message.answer(
        texts.event_registered(event)
        + f"\n\nЗарегистрировано: {stats['registered']}"
        + (f"\nСвободных мест: {stats['free']}" if event.participant_limit is not None else "")
    )
