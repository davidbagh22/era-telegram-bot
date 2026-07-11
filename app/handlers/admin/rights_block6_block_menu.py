from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.handlers.admin.rights_block6 import _guard

router = Router(name="admin_rights_block6_block_menu")


@router.callback_query(F.data.regexp(r"^admin:user:block_menu:\d+$"))
async def block_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings, manage=True):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    target = await session.get(User, target_id)
    if not target:
        await call.message.answer("Участник не найден")
        return
    rows = []
    if target.is_blocked:
        rows.append([InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin:user:unblock:{target.id}")])
    else:
        rows.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:user:block:{target.id}")])
    rows.append([InlineKeyboardButton(text="← К участнику", callback_data=f"admin:user:{target.id}")])
    await call.message.answer(
        f"Доступ участника: {'заблокирован' if target.is_blocked else 'активен'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
