from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.partners import Partner
from app.keyboards.partners import admin_partners_keyboard
from app.utils.constants import Role

router = Router(name="admin_partners")


def admin_ok(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids or bool(user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)


@router.callback_query(F.data == "admin:partners")
async def list_partners(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partners = (await session.scalars(select(Partner).where(Partner.is_archived.is_(False)).order_by(Partner.name))).all()
    await call.message.answer("🤝 Партнёры\n\nУправление партнёрами ЭРА.", reply_markup=admin_partners_keyboard(partners))
