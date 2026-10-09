from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User

router = Router(name="book_club")


def _keyboard(subscribed: bool = False) -> InlineKeyboardMarkup:
    if subscribed:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔕 Отписаться от программы", callback_data="bookclub:unsubscribe")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Вступить в программу на 48 дней", callback_data="bookclub:subscribe")],
    ])


@router.message(F.text.in_({"📖 Книжный клуб", "📚 Литература"}))
async def book_club(message: Message, user: User | None) -> None:
    subscribed = bool(user and user.book_club_subscribed)
    status = "Вы подписаны на ежедневные материалы." if subscribed else "Подписка добровольная."
    await message.answer(
        "📚 ЭРА | Литература\n\n48 дней. 48 законов. 48 решений. "
        "Авторские разборы идей книги «48 законов власти», практические ситуации "
        "и вопросы для обсуждения. Не текст книги.\n\n" + status,
        reply_markup=_keyboard(subscribed),
    )


@router.callback_query(F.data.in_({"bookclub:subscribe", "bookclub:unsubscribe"}))
async def change_subscription(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if user is None:
        await call.answer("Сначала завершите регистрацию в боте.", show_alert=True)
        return
    subscribed = call.data == "bookclub:subscribe"
    if user.book_club_subscribed != subscribed:
        user.book_club_subscribed = subscribed
        await session.commit()
    await call.answer("Подписка включена" if subscribed else "Подписка отключена")
    await call.message.answer(
        "✅ Вы подписаны на ежедневные материалы." if subscribed
        else "🔕 Подписка отключена. Ежедневные сообщения больше не будут отправляться.",
        reply_markup=_keyboard(subscribed),
    )
