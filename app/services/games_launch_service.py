"""One-time game-room menu and launch notification; disabled until rollout approval."""
from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.handlers.era_game_room import menu_markup
from app.services.general_topics_service import ensure_topic, send_general_topic, send_general_topic_once

logger = logging.getLogger(__name__)


async def refresh_games_pin(bot, settings, session_factory, thread_id: int) -> bool:
    """Adopt only an observed, bot-owned game pin; never guess or duplicate its ID."""
    import hashlib
    from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
    from sqlalchemy import select
    from app.database.models import AppSetting
    from app.handlers.era_game_room import _data, _lock, _save, PUBLIC_MENU_TEXT

    key = f"games-menu-card:{settings.general_chat_id}:{thread_id}"
    markup = menu_markup(public=True, bot_username=settings.bot_username or "ERA_1bot")
    version = hashlib.sha256((PUBLIC_MENU_TEXT + markup.model_dump_json()).encode()).hexdigest()
    async with session_factory() as session:
        await _lock(session, key)
        state = _data(await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()))
        confirmed = state.get("version") == version and state.get("status") == "confirmed"
        if state.get("revision") != version:
            state["attempts"] = 0
            state["revision"] = version
        if state.get("attempts", 0) >= 3:
            return False
        state["attempts"] = state.get("attempts", 0) + 1
        try:
            message_id = state.get("message_id")
            if not message_id:
                me = await bot.get_me()
                chat = await bot.get_chat(settings.general_chat_id)
                pinned = getattr(chat, "pinned_message", None)
                if not (pinned and pinned.from_user and pinned.from_user.id == me.id
                        and pinned.message_thread_id == thread_id
                        and (pinned.text or "").startswith("🎮 ЭРА | Интерактив")):
                    logger.warning("Game menu needs reconciliation: no observed game pin")
                    return False
                message_id = pinned.message_id
                state["message_id"] = message_id
            await _save(session, key, state)
            try:
                await bot.edit_message_text(chat_id=settings.general_chat_id, message_id=message_id,
                                            text=PUBLIC_MENU_TEXT, parse_mode="HTML", reply_markup=markup)
            except TelegramBadRequest as exc:
                if "message to edit not found" in str(exc).lower():
                    state.pop("message_id", None)
                    state.update(status="missing", replacement_for=message_id, attempts=0)
                    await _save(session, key, state)
                    await session.commit()
                    return False
                if "not modified" not in str(exc).lower():
                    raise
            if not confirmed:
                await bot.pin_chat_message(chat_id=settings.general_chat_id, message_id=message_id,
                                           disable_notification=True)
            state.update(status="confirmed", version=version, attempts=0)
            await _save(session, key, state)
            await session.commit()
            logger.info("Game menu refreshed and pin confirmed")
            return True
        except TelegramAPIError as exc:
            state["status"] = "needs_attention"
            state["error_code"] = type(exc).__name__
            state["attempts"] = max(1, state.get("attempts", 0))
            await _save(session, key, state)
            await session.commit()
            logger.warning("Game menu pin postponed type=%s", type(exc).__name__)
            return False


async def publish_games_launch(bot, settings, session_factory) -> None:
    if settings.feature_games != "ALL" or not settings.general_chat_id:
        return
    thread_id = await ensure_topic(bot, settings, "games", session_factory=session_factory)
    if thread_id is None:
        logger.warning("Games launch postponed: game topic unavailable")
        return

    menu_ok = await refresh_games_pin(bot, settings, session_factory, thread_id)
    if not menu_ok:
        # If another pin hides the old menu, publish this UX edition once through
        # the existing delivery ledger. An ambiguous receipt is never replayed.
        from sqlalchemy import select
        from app.database.models import AppSetting
        from app.handlers.era_game_room import _data, _lock, _save, PUBLIC_MENU_TEXT
        key = f"games-menu-card:{settings.general_chat_id}:{thread_id}"
        async with session_factory() as session:
            await _lock(session, key)
            state = _data(await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()))
            if state.get("message_id"):
                logger.warning("Game menu is available but pin confirmation needs attention")
                return
            outcome = await send_general_topic_once(
                bot, settings, "games", PUBLIC_MENU_TEXT, parse_mode="HTML",
                reply_markup=menu_markup(public=True, bot_username=settings.bot_username or "ERA_1bot"),
                delivery_key=(f"games-menu-identity-v2:replace:{state['replacement_for']}"
                              if state.get("replacement_for") else "games-menu-identity-v2"),
            )
            if not outcome.sent or not outcome.message_id:
                logger.warning("Games menu edition not reconciled status=%s", outcome.status)
                return
            state.update(message_id=outcome.message_id, attempts=0, status="observed")
            await _save(session, key, state)
            await session.commit()
        menu_ok = await refresh_games_pin(bot, settings, session_factory, thread_id)
        if not menu_ok:
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
        "Тебя ждут 12 форматов: быстрый и командный квиз, «Правда или миф», «Шпион», "
        "угадай страну, хронология, словесная цепочка, ассоциации, логика, "
        "культурный блиц, память и командная дуэль.\n\n"
        "Можно начать одному или собрать команду. Все игры проходят в теме «🎮 Интерактив». "
        "Выбирай формат и играй прямо в Telegram 👇",
        parse_mode="HTML", reply_markup=keyboard,
        delivery_key="games-notification-v1",
    )
