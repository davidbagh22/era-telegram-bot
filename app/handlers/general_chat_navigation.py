from __future__ import annotations

from aiogram import F, Bot, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.faq import GENERAL_CHAT_EVENTS_TEXT, GENERAL_CHAT_PROFILE_TEXT
from app.keyboards.participant import event_list_keyboard
from app.services.chat_access_service import chat_key_for_id, check_chat_access
from app.services.event_service import published_events
from app.services.notification_service import safe_send
from app.utils.deep_links import miniapp_profile_url

router = Router(name="general_chat_navigation")


async def _delete_quick_action_message(message: Message) -> None:
    """Keep the shared chat clean after a reply-keyboard tap."""
    try:
        await message.delete()
    except TelegramAPIError:
        # The action still works if the bot temporarily lacks delete rights.
        pass


def _is_general_chat(message: Message, settings: Settings) -> bool:
    return chat_key_for_id(settings, message.chat.id) == "general"


def _can_use_general_chat(user: User | None) -> bool:
    return check_chat_access(user, "general").allowed


@router.message(
    F.text == GENERAL_CHAT_EVENTS_TEXT,
    ~F.chat.type.in_({"private"}),
)
async def open_events_from_general_chat(
    message: Message,
    bot: Bot,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Show the actual current event list in the participant's bot DM.

    The group button itself only emits text because Telegram does not permit a
    group reply-keyboard WebApp button. We immediately remove that service text
    and continue privately, so the general chat remains a community feed rather
    than a navigation log.
    """
    if not _is_general_chat(message, settings) or not _can_use_general_chat(user):
        raise SkipHandler

    await _delete_quick_action_message(message)
    if user is None:
        return

    events = await published_events(session)
    if not events:
        await safe_send(
            bot,
            user.telegram_id,
            "📅 События ЭРА\n\nСейчас нет открытых мероприятий. Новые события появятся здесь сразу после публикации.",
        )
        return

    await safe_send(
        bot,
        user.telegram_id,
        "📅 События ЭРА\n\nВыберите мероприятие — подробности и регистрация откроются прямо здесь, в боте.",
        reply_markup=event_list_keyboard(events),
    )


@router.message(
    F.text == GENERAL_CHAT_PROFILE_TEXT,
    ~F.chat.type.in_({"private"}),
)
async def open_profile_from_general_chat(
    message: Message,
    bot: Bot,
    user: User | None,
    settings: Settings,
) -> None:
    """Hand off from the shared chat to the participant's profile Mini App."""
    if not _is_general_chat(message, settings) or not _can_use_general_chat(user):
        raise SkipHandler

    await _delete_quick_action_message(message)
    if user is None:
        return

    profile_url = miniapp_profile_url(settings.effective_miniapp_url)
    if not profile_url:
        await safe_send(
            bot,
            user.telegram_id,
            "🔥 Моя ЭРА временно недоступна. Попробуйте открыть приложение немного позже.",
        )
        return

    await safe_send(
        bot,
        user.telegram_id,
        "🔥 Моя ЭРА\n\nВаш путь, баллы, проекты, достижения и личный профиль — здесь.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть Моя ЭРА",
                        web_app=WebAppInfo(url=profile_url),
                    )
                ]
            ]
        ),
    )
