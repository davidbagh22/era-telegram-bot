"""In-chat FAQ card for the general chat (2026-08 master spec, P5) -- an
admin-triggered "post + pin" action (Admin Mode -> Чаты) and the
callback_data -> canned-answer mapping the bot uses when someone taps a
button. Every answer goes to the tapper's own DM (see
app/handlers/chat_faq.py) -- this module never posts anything back into
the group beyond the one pinned card itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.keyboards.faq import faq_keyboard
from app.services.audit_service import audit
from app.utils import texts

# Single source of truth for what each FAQ button answers -- callback_data
# values must match app/keyboards/faq.py exactly.
FAQ_ANSWERS: dict[str, str] = {
    "faq:what_is_era": texts.FAQ_ANSWER_WHAT_IS_ERA,
    "faq:what_it_gives": texts.FAQ_ANSWER_WHAT_IT_GIVES,
    "faq:what_can_i_do": texts.FAQ_ANSWER_WHAT_CAN_I_DO,
    "faq:what_to_do": texts.FAQ_ANSWER_WHAT_TO_DO,
}


class ChatFaqError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class FaqPublishResult:
    pinned: bool


async def publish_faq_message(
    bot: Bot, settings: Settings, session: AsyncSession, actor_id: int | None
) -> FaqPublishResult:
    chat_id = settings.general_chat_id
    if not chat_id:
        raise ChatFaqError("chat_not_bound")
    try:
        sent = await bot.send_message(chat_id, texts.FAQ_PINNED_MESSAGE, reply_markup=faq_keyboard())
    except TelegramAPIError as exc:
        raise ChatFaqError(f"send_failed:{str(exc)[:200]}") from exc
    pinned = True
    try:
        await bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
    except TelegramAPIError:
        # The card is posted either way -- pin needs the bot to be an admin
        # with pin rights, which the Chat Registry's health check already
        # surfaces separately. Not fatal: an unpinned FAQ card is still
        # usable, just easier to scroll past.
        pinned = False
    await audit(
        session,
        actor_id=actor_id,
        action="chat.faq_published",
        entity_type="chat",
        entity_id=None,
        new_value={"chat": "general", "pinned": pinned},
    )
    return FaqPublishResult(pinned=pinned)
