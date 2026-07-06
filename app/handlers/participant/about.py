from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.models import User
from app.keyboards.participant import about_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="about")

ABOUT_TEXT = """ℹ️ Что умеет бот ЭРА

Это Ваш личный кабинет внутри сообщества. Здесь участник не просто смотрит новости, а двигается: приходит на мероприятия, берёт задачи, предлагает проекты, получает баллы и фиксирует рост.

👤 Личный кабинет
Профиль, «Баллы и достижения» (баланс, рейтинг, знаки) и «Мой путь» (портфолио, мероприятия, проекты, направления, задачи).

📅 Афиша
Ближайшие мероприятия ЭРА, регистрация и участие.

💡 Проекты
Пошаговый конструктор проекта, черновики и отправка идеи команде ЭРА. На каждом этапе можно получить подсказку.

⭐ Возможности
Каталог возможностей, аукционы, награды и баллы за реальный вклад.

💬 Связь
Вопросы команде, департаменты, контакты, правила и информация о боте.

⚙️ Панель
Рабочий раздел для лидеров и администраторов. Он появляется только у тех, кому выданы права."""


async def _send_about(message: Message, user: User | None) -> None:
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(ABOUT_TEXT, reply_markup=about_keyboard())


@router.message(F.text == "ℹ️ О боте")
@router.message(Command("about"), F.chat.type == "private")
@router.message(Command("help"), F.chat.type == "private")
async def about_button(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    await _send_about(message, user)


@router.callback_query(F.data == "about:open")
async def about_callback(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    await _send_about(call.message, user)
