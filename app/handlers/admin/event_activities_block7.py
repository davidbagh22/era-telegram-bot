from datetime import datetime, timedelta

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventActivitySubmission, EventRegistration, PointTransaction, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import RegistrationStatus, Role
from app.utils.validators import clean_text

router = Router(name="admin_event_activities_block7")


class ActivityAdminStates(StatesGroup):
    create_lines = State()


def is_admin(user: User | None, settings: Settings, tg_id: int) -> bool:
    return bool(tg_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


async def guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        tg_id = event.from_user.id
    else:
        message = event
        tg_id = event.from_user.id
    if not is_admin(user, settings, tg_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def event_activity_buttons(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать активности", callback_data=f"admin:event:activities:create:{event_id}")],
        [InlineKeyboardButton(text="📤 Отправить активности участникам", callback_data=f"admin:event:activities:send:{event_id}")],
        [InlineKeyboardButton(text="📥 Активности на проверке", callback_data="admin:event_activities:review")],
    ])


def submit_button(activity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📤 Отправить результат", callback_data=f"activity:submit:{activity_id}")]])


def review_buttons(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Начислить баллы", callback_data=f"admin:activity:approve:{sub_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:activity:reject:{sub_id}")],
    ])


@router.callback_query(F.data.startswith("admin:event:activities:create:"))
async def create_start(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    await state.set_state(ActivityAdminStates.create_lines)
    await state.update_data(activity_event_id=event.id)
    await call.message.answer(
        "Отправьте активности списком. Одна строка = одна активность.\n\n"
        "Формат:\n"
        "Название | баллы | тип | описание\n\n"
        "Пример:\n"
        "Сделать фото | 10 | photo | Прикрепите фото с мероприятия\n"
        "Написать отзыв | 5 | text | Напишите короткий отзыв"
    )


@router.message(ActivityAdminStates.create_lines)
async def create_finish(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await guard(message, user, settings):
        return
    data = await state.get_data()
    event = await session.get(Event, int(data["activity_event_id"]))
    if not event:
        await state.clear()
        await message.answer("Мероприятие не найдено")
        return
    created = 0
    for raw_line in (message.text or "").splitlines():
        parts = [part.strip() for part in raw_line.split("|")]
        if len(parts) < 3:
            continue
        title = clean_text(parts[0], 255)
        try:
            points = int(parts[1])
        except ValueError:
            continue
        submission_type = clean_text(parts[2], 32) or "text"
        description = clean_text(parts[3], 1000) if len(parts) > 3 else title
        if not title or points < 0 or points > 1000:
            continue
        session.add(EventActivity(
            event_id=event.id,
            title=title,
            description=description or title,
            submission_type=submission_type,
            points=points,
            requires_review=True,
            deadline=datetime.now().astimezone() + timedelta(days=7),
            is_active=True,
        ))
        created += 1
    await state.clear()
    if not created:
        await message.answer("Не удалось создать активности. Проверьте формат строк.")
        return
    await message.answer(f"Создано активностей: {created}", reply_markup=event_activity_buttons(event.id))


@router.callback_query(F.data.startswith("admin:event:activities:send:"))
async def send_to_registered(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    event_id = int(call.data.rsplit(":", 1)[-1])
    event = await session.get(Event, event_id)
    activities = (await session.scalars(select(EventActivity).where(EventActivity.event_id == event_id, EventActivity.is_active == True))).all()
    if not event or not activities:
        await call.message.answer("Мероприятие или активности не найдены")
        return
    registrations = (await session.scalars(select(EventRegistration).where(EventRegistration.event_id == event_id, EventRegistration.status.in_([RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME, RegistrationStatus.ATTENDED])))).all()
    sent = 0
    for registration in registrations:
        target = await session.get(User, registration.user_id)
        if not target:
            continue
        for activity in activities:
            await safe_send(
                bot,
                target.telegram_id,
                f"✨ Активность после мероприятия\n\n{event.title}\n\n{activity.title}\n{activity.description}\n\nФормат: {activity.submission_type}\nБаллы: {activity.points}",
                reply_markup=submit_button(activity.id),
            )
        sent += 1
    await call.message.answer(f"Активности отправлены участникам: {sent}. Отменившим регистрацию не отправлял.")


async def send_submission_card(message: Message, session: AsyncSession, sub: EventActivitySubmission) -> None:
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    if not activity or not target:
        return
    await message.answer(
        f"📥 Активность #{sub.id}\n\n{activity.title}\nУчастник: {target.first_name} {target.last_name or ''}\nСтатус: {sub.status}\nБаллы: {activity.points}\n\n{sub.text or 'материал прикреплён файлом'}",
        reply_markup=review_buttons(sub.id),
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
            await message.answer("Файл прикреплён, но Telegram не дал открыть его повторно")


@router.callback_query(F.data == "admin:event_activities:review")
async def review_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    items = (await session.scalars(select(EventActivitySubmission).where(EventActivitySubmission.status.in_(["pending", "leader_approved"])).order_by(EventActivitySubmission.created_at).limit(50))).all()
    if not items:
        await call.message.answer("Активностей на проверке нет")
        return
    await call.message.answer(f"Активности на проверке: {len(items)}")
    for sub in items:
        await send_submission_card(call.message, session, sub)


@router.callback_query(F.data.startswith("admin:activity:approve:"))
async def approve(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    sub = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not sub or sub.status not in {"pending", "leader_approved"}:
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    if not activity or not target:
        await call.message.answer("Активность или участник не найдены")
        return
    if sub.points_awarded > 0:
        sub.status = "approved"
        await call.message.answer("Ответ принят. Баллы уже начислялись ранее, повторно не начисляю.")
        return
    existing = await session.scalar(select(PointTransaction).where(PointTransaction.user_id == sub.user_id, PointTransaction.related_event_id == activity.event_id, PointTransaction.reason.ilike(f"%{activity.title}%"), PointTransaction.points > 0))
    sub.status = "approved"
    sub.reviewed_by = user.id if user else None
    if existing:
        await call.message.answer("Ответ принят. Баллы за эту активность уже начислялись ранее.")
        return
    sub.points_awarded = activity.points
    await add_points(session, user_id=sub.user_id, points=activity.points, reason=f"Активность после мероприятия: {activity.title}", approved_by=user.id if user else None, related_event_id=activity.event_id)
    await safe_send(bot, target.telegram_id, f"Ваш результат «{activity.title}» принят — начислено {activity.points} баллов")
    await call.message.answer("Активность принята. Баллы начислены один раз.")


@router.callback_query(F.data.startswith("admin:activity:reject:"))
async def reject(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    sub = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not sub or sub.status == "approved":
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    sub.status = "rejected"
    sub.reviewed_by = user.id if user else None
    if target and activity:
        await safe_send(bot, target.telegram_id, f"Результат «{activity.title}» не принят. Баллы не начислены.")
    await call.message.answer("Активность отклонена. Баллы не начислены.")
