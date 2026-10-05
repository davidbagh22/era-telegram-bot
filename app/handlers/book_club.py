from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User

router = Router(name="book_club")

def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📖 Подписаться на 48 дней", callback_data="bookclub:subscribe")]])

@router.message(F.text == "📖 Книжный клуб")
async def book_club(message: Message, user: User | None) -> None:
    await message.answer("📖 Книжный клуб ЭРА\n\n48 дней — 48 авторских пересказов идей книги «48 законов власти», практические вопросы и обсуждение. Полный текст книги не рассылаем: читайте её в своём экземпляре или легальном источнике.", reply_markup=_keyboard())

@router.callback_query(F.data == "bookclub:subscribe")
async def subscribe(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if user is None:
        await call.message.answer("Сначала запустите бота и завершите регистрацию.")
        return
    user.book_club_subscribed = True
    await session.commit()
    await call.message.answer("Готово ✅ Вы получите один авторский разбор в день в течение 48 дней и сможете обсуждать его с участниками.")
