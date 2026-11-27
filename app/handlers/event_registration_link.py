"""Open an existing published event's registration card via /start event_<id>.

This is a navigation shortcut only: no registration is written before the
participant explicitly confirms using the normal event:join handler. A newcomer
keeps an unfinished application draft, and the event is remembered for them.
"""
from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.handlers.participant.events_stability_block8 import show_public_event_registration_card
from app.utils.deep_links import parse_event_registration_payload

router = Router(name="event_registration_link")
router.message.filter(F.chat.type == "private")


@router.message(
    StateFilter("*"),
    CommandStart(),
    F.text.regexp(r"^/start(?:@\w+)?\s+event_[0-9]+\s*$"),
)
async def open_event_registration(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    event_id = parse_event_registration_payload((command.args or "").strip())
    current_state = await state.get_state()
    resume_registration = bool(
        current_state
        and current_state.startswith("RegistrationStates:")
        and (user is None or user.application_status in {"rejected", "needs_info"})
    )
    if not resume_registration:
        await state.clear()
    await show_public_event_registration_card(
        message, user, session, event_id, settings=settings, telegram_id=message.from_user.id,
        resume_registration=resume_registration,
    )
