from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import EventActivity, EventActivitySubmission, User
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_activity_files")


def ok(u: User | None, s: Settings, tg_id: int) -> bool:
    return bool(tg_id in s.admin_ids or (u and u.role == Role.ADMIN and not u.is_blocked))


def actions(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Принять", callback_data=f"admin:activity:approve:{sub_id}"),
            InlineKeyboardButton(text="Не принимать", callback_data=f"admin:activity:reject:{sub_id}"),
        ]]
    )


async def card(message: Message, session: AsyncSession, sub: EventActivitySubmission) -> None:
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    if not activity:
        return
    name = f"{target.first_name} {target.last_name or ''}" if target else str(sub.user_id)
    await message.answer(
        f"✨ {activity.title}\n\n"
        f"Участник: {name}\n"
        f"Статус: {sub.status}\n"
        f"Награда: {activity.points} баллов\n\n"
        f"Ответ:\n{sub.text or 'текст не прикреплён'}",
        reply_markup=actions(sub.id),
    )
    if sub.file_id:
        try:
            if sub.file_type == "photo":
                await message.answer_photo(sub.file_id, caption="Материал участника")
            elif sub.file_type == "video":
                await message.answer_video(sub.file_id, caption="Материал участника")
            else:
                await message.answer_document(sub.file_id, caption="Материал участника")
        except Exception:
            await message.answer("Материал прикреплён, но его не удалось открыть повторно")


@router.callback_query(F.data == "admin:event_activities")
async def list_activity_submissions(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not ok(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    items = (
        await session.scalars(
            select(EventActivitySubmission)
            .where(EventActivitySubmission.status == "pending")
            .order_by(EventActivitySubmission.created_at)
            .limit(50)
        )
    ).all()
    if not items:
        await call.message.answer("Новых ответов на проверке нет")
        return
    await call.message.answer(f"Ответы на проверке: {len(items)}")
    for sub in items:
        await card(call.message, session, sub)
