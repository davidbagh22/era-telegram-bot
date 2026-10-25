from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database.models import User
from app.keyboards.participant import open_app_button
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="about")

# 2026-08 bot cleanup: this used to be a feature-list ("👤 Личный
# кабинет / 📅 Афиша / 💡 Проекты / ...") ending in about_keyboard() — a
# 6-button bot-native menu duplicating the Mini App, reachable from
# "💬 Связь" → "ℹ️ О боте" (contact_keyboard()'s about:open button). Now
# a short paragraph pointing at "🧭 Навигация" for the actual breakdown,
# same as /help (see commands_ready.py's help_command, which now wins
# the live /help registration — this file keeps /about only, since
# "что умеет бот" and "куда идти" are the same answer now).
ABOUT_TEXT = (
    "ℹ️ О боте ЭРА\n\n"
    "Бот — это вход в сообщество: регистрация, уведомления и связь с командой. "
    "Вся работа — проекты, задачи, мероприятия, возможности, профиль — происходит "
    "в приложении ЭРА.\n\n"
    "Разбор по разделам: «🧭 Навигация»."
)


async def _send_about(message: Message, user: User | None, settings: Settings) -> None:
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(ABOUT_TEXT, reply_markup=open_app_button(settings.effective_miniapp_url))


@router.message(F.text == "ℹ️ О боте")
@router.message(Command("about"), F.chat.type == "private")
async def about_button(
    message: Message, user: User | None, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    await _send_about(message, user, settings)


@router.callback_query(F.data == "about:open")
async def about_callback(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    await _send_about(call.message, user, settings)
