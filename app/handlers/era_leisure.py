"""Unified leisure navigation in private bot chat.

Legacy literature entry points stay supported; games remain feature-gated.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Settings
from app.services.general_topics_service import ensure_topic

router = Router(name="era_leisure")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


async def _markup(bot, settings: Settings) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📚 Литература · 48 законов", callback_data="bookclub:home")]]
    if settings.feature_games == "ALL" and settings.general_chat_id:
        thread_id = await ensure_topic(bot, settings, "games")
        chat_id = str(settings.general_chat_id)
        if thread_id and chat_id.startswith("-100"):
            rows.append([InlineKeyboardButton(
                text="🎮 Игровая · квизы и команды",
                url=f"https://t.me/c/{chat_id[4:]}/{thread_id}",
            )])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_leisure(message: Message, settings: Settings) -> None:
    await message.answer(
        "🎲 <b>ЭРА | Досуг</b>\n\n"
        "📚 <b>Литература</b> — ежедневные разборы, обсуждения и задания.\n"
        "🎮 <b>Игровая</b> — быстрые квизы и командные игры в общем чате.\n\n"
        "Выбирай, чем заняться!",
        reply_markup=await _markup(message.bot, settings),
        parse_mode="HTML",
    )


@router.message(F.text.in_({"🎲 Досуг", "🎭 Развлечения"}))
async def leisure_message(message: Message, settings: Settings):
    await show_leisure(message, settings)


@router.callback_query(F.data == "leisure:home")
async def leisure_callback(call: CallbackQuery, settings: Settings):
    await call.answer()
    await show_leisure(call.message, settings)
