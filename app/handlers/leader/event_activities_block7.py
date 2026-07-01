from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventActivitySubmission, User
from app.services.notification_service import notify_admins, safe_send
from app.utils import texts
from app.utils.constants import PRIVILEGED_ROLES

router = Router(name="leader_event_activities_block7")


def is_leader(user: User | None) -> bool:
    return bool(user and not user.is_blocked and user.role in PRIVILEGED_ROLES)


def review_buttons(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Лидер принял", callback_data=f"leader:activity:approve:{sub_id}")],
        [InlineKeyboardButton(text="❌ Лидер отклонил", callback_data=f"leader:activity:reject:{sub_id}")],
    ])


async def guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if not is_leader(user):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


async def send_card(call: CallbackQuery, session: AsyncSession, sub: EventActivitySubmission) -> None:
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    if not activity or not target:
        return
    await call.message.answer(
        f"✨ Активность #{sub.id}\n\n{activity.title}\nУчастник: {target.first_name} {target.last_name or ''}\nСтатус: {sub.status}\nБаллы: {activity.points}\n\n{sub.text or 'материал прикреплён файлом'}",
        reply_markup=review_buttons(sub.id),
    )
    if sub.file_id:
        try:
            if sub.file_type == "photo":
                await call.message.answer_photo(sub.file_id, caption="Материал участника")
            elif sub.file_type == "video":
                await call.message.answer_video(sub.file_id, caption="Материал участника")
            else:
                await call.message.answer_document(sub.file_id, caption="Материал участника")
        except Exception:
            await call.message.answer("Файл не удалось открыть повторно")


@router.callback_query(F.data == "leader:event_activities")
async def list_for_leader(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await guard(call, user):
        return
    events = (await session.scalars(select(Event).where(Event.responsible_id == user.id))).all()
    event_ids = [event.id for event in events]
    if not event_ids:
        await call.message.answer("У Вас пока нет мероприятий для проверки активностей")
        return
    activities = (await session.scalars(select(EventActivity).where(EventActivity.event_id.in_(event_ids)))).all()
    activity_ids = [activity.id for activity in activities]
    items = (await session.scalars(select(EventActivitySubmission).where(EventActivitySubmission.activity_id.in_(activity_ids or [-1]), EventActivitySubmission.status == "pending").order_by(EventActivitySubmission.created_at).limit(50))).all()
    if not items:
        await call.message.answer("Новых активностей на лидерской проверке нет")
        return
    await call.message.answer(f"Активности на проверке: {len(items)}")
    for sub in items:
        await send_card(call, session, sub)


@router.callback_query(F.data.startswith("leader:activity:approve:"))
async def leader_approve(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user):
        return
    sub = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not sub or sub.status != "pending":
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    sub.status = "leader_approved"
    sub.reviewed_by = user.id
    await call.message.answer("Активность принята лидером и отправлена админу на финальное начисление.")
    if activity:
        await notify_admins(bot, settings, f"✨ Активность прошла лидерскую проверку\n\n{activity.title}\nТеперь админ может финально начислить баллы.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Открыть проверку", callback_data="admin:event_activities:review")]]))
    if target and activity:
        await safe_send(bot, target.telegram_id, f"Ваш результат «{activity.title}» принят лидером и передан админу на финальное подтверждение.")


@router.callback_query(F.data.startswith("leader:activity:reject:"))
async def leader_reject(call: CallbackQuery, user: User | None, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user):
        return
    sub = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not sub or sub.status != "pending":
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    sub.status = "rejected"
    sub.reviewed_by = user.id
    if target and activity:
        await safe_send(bot, target.telegram_id, f"Результат «{activity.title}» не прошёл лидерскую проверку.")
    await call.message.answer("Активность отклонена лидером.")
