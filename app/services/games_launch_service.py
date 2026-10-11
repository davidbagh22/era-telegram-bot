"""One-time game-room menu and launch notification; disabled until rollout approval."""
from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.handlers.era_game_room import menu_markup
from app.services.general_topics_service import ensure_topic, send_general_topic

logger = logging.getLogger(__name__)


async def publish_games_launch(bot, settings, session_factory) -> None:
    if settings.feature_games != "ALL" or not settings.general_chat_id:
        return
    thread_id = await ensure_topic(bot, settings, "games", session_factory=session_factory)
    if thread_id is None:
        logger.warning("Games launch postponed: game topic unavailable")
        return

    menu_ok = await send_general_topic(
        bot, settings, "games",
        "🎮 <b>ЭРА | Интерактив</b>\n\n"
        "Небольшая компания — уже повод поиграть. Можно пройти короткий квиз "
        "или собрать команду. Игры доступны здесь в любое время.\n\n"
        "Выбирай формат ниже 👇",
        parse_mode="HTML",
        reply_markup=menu_markup(),
        delivery_key="games-menu-v1",
    )
    if not menu_ok:
        logger.warning("Games launch postponed: menu not confirmed")
        return

    # Telegram forum topic link for a private supergroup; do not publish if ID invalid.
    chat_id = str(settings.general_chat_id)
    if not chat_id.startswith("-100") or not str(thread_id).isdigit():
        logger.warning("Games launch notification postponed: topic link unavailable")
        return
    topic_url = f"https://t.me/c/{chat_id[4:]}/{thread_id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎮 Перейти в Интерактив", url=topic_url)
    ]])
    await send_general_topic(
        bot, settings, "notifications",
        "🎮 <b>В ЭРА появился Интерактив!</b>\n\n"
        "Теперь в общем чате можно пройти быстрый квиз или собрать команду. "
        "Не нужно ждать большой компании: выбирай удобный формат и играй, когда захочешь.\n\n"
        "Игры и все обсуждения проходят только в теме «Интерактив».",
        parse_mode="HTML", reply_markup=keyboard,
        delivery_key="games-notification-v1",
    )
