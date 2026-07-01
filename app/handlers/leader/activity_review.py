from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventActivitySubmission, User
from app.services.notification_service import notify_admins, safe_send
from app.utils import texts
from app.utils.constants import PRIVILEGED_ROLES

router = Router(name="leader_activity_review")


def is_leader(user: User | None) -> bool:
    return bool(user and not user.is_blocked and user.role in PRIVILEGED_ROLES)


def actions(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Лидер принял", callback_data=f"leader:activity:approve:{sub_id}"),
        InlineKeyboardButton(text="❌ Лидер отклонил", callback_data=f"leader:activity:reject:{sub_id}"),
    ]])


@router.callback_query(F.data == "leader:event_activities")
async def leader_activity_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not is_leader(user):
        await call.message.answer(texts.NO_ACCESS)
        return
    events = (await session.scalars(select(Event).where(Event.responsible_id == user.id))).all()
    event_ids = [event.id for event in events]
    if not event_ids:
        await call.message.answer("У Вас пока нет мероприятий для проверки активностей")
        return
    activities = (await session.scalars(select(EventActivity).where(EventActivity.event_id.in_(event_ids)))).all()
    activity_ids = [item.id for item in activities]
    items = (await session.scalars(select(EventActivitySubmission).where(EventActivitySubmission.activity_id.in_(activity_ids or [-1]), EventActivitySubmission.status == "pending"))).all()
    if not items:
        await call.message.answer("Новых активностей на проверке у Вас нет")
        return
    await call.message.answer(f"Активности на лидерской проверке: {len(items)}")
    for sub in items:
        activity = await session.get(EventActivity, sub.activity_id)
        target = await session.get(User, sub.user_id)
        if not activity:
            continue
        await call.message.answer(
            f"✨ {activity.title}\n\nУчастник: {target.first_name if target else sub.user_id}\nБаллы: {activity.points}\n\n{sub.text or 'материал прикреплён файлом'}",
            reply_markup=actions(sub.id),
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


@router.callback_query(F.data.regexp(r"^leader:activity:(approve|reject):\d+$"))
async def leader_activity_decide(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not is_leader(user):
        await call.message.answer(texts.NO_ACCESS)
        return
    _, _, action, raw_id = call.data.split(":")
    sub = await session.get(EventActivitySubmission, int(raw_id))
    if not sub or sub.status != "pending":
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    if action == "reject":
        sub.status = "rejected"
        sub.reviewed_by = user.id
        if target and activity:
            await safe_send(bot, target.telegram_id, f"Результат «{activity.title}» не прошёл лидерскую проверку")
        await call.message.answer("Ответ отклонён лидером")
        return
    sub.status = "leader_approved"
    sub.reviewed_by = user.id
    await call.message.answer("Ответ принят лидером и отправлен админу на финальное начисление")
    if activity:
        await notify_admins(bot, settings, f"✨ Активность прошла лидерскую проверку\n\n{activity.title}\nТеперь админ может финально начислить баллы.")
