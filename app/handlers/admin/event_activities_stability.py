from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventActivitySubmission, PointTransaction, User
from app.handlers.admin.event_activities_block15 import ActivitySetupStates
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import EventStatus, Role
from app.utils.validators import clean_text

router = Router(name="admin_event_activities_stability")

ALLOWED_TYPES = {"photo", "link", "text", "file", "video", "manual"}
REVIEWABLE_ACTIVITY_STATUSES = {"pending", "leader_approved"}


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (
            user
            and not user.is_blocked
            and not user.is_archived
            and any(
                grant.is_active and grant.permission == "events.manage"
                for grant in (user.permission_grants or [])
            )
        )
    )


async def _guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _manage_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить активности", callback_data=f"admin:event:activities:create:{event_id}")],
            [InlineKeyboardButton(text="📤 Отправить участникам", callback_data=f"admin:event:activities:send:{event_id}")],
            [InlineKeyboardButton(text="📥 На проверке", callback_data="admin:event_activities:review")],
            [InlineKeyboardButton(text="← Мероприятия", callback_data="admin:events")],
        ]
    )


def _review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить и начислить баллы", callback_data=f"admin:activity:approve:{submission_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:activity:reject:{submission_id}")],
        ]
    )


async def _send_file(message: Message, submission: EventActivitySubmission) -> None:
    if not submission.file_id:
        return
    try:
        if submission.file_type == "photo":
            await message.answer_photo(submission.file_id, caption="Подтверждение активности")
        elif submission.file_type == "video":
            await message.answer_video(submission.file_id, caption="Подтверждение активности")
        else:
            await message.answer_document(submission.file_id, caption="Подтверждение активности")
    except Exception:
        await message.answer("Файл сохранён, но Telegram не смог открыть его повторно")


@router.callback_query(F.data == "admin:event_activities")
async def activities_home(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    pending_count = int(
        await session.scalar(
            select(func.count())
            .select_from(EventActivitySubmission)
            .where(EventActivitySubmission.status.in_(REVIEWABLE_ACTIVITY_STATUSES))
        )
        or 0
    )
    events = list(
        (
            await session.scalars(
                select(Event)
                .where(Event.status == EventStatus.COMPLETED)
                .order_by(Event.event_date.desc(), Event.event_time.desc())
                .limit(20)
            )
        ).all()
    )
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"📥 На проверке · {pending_count}", callback_data="admin:event_activities:review")]
    ]
    for event in events:
        label = f"{event.event_date:%d.%m} · {event.title[:35]}"
        rows.append([InlineKeyboardButton(text=f"➕ {label}", callback_data=f"admin:event:activities:create:{event.id}")])
        rows.append([InlineKeyboardButton(text=f"📤 {label}", callback_data=f"admin:event:activities:send:{event.id}")])
    rows.append([InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")])
    text = (
        "✨ Активности после мероприятий\n\n"
        f"На проверке: {pending_count}\n"
        f"Завершённых мероприятий для настройки: {len(events)}\n\n"
        "Выберите мероприятие, чтобы добавить задания после события или отправить их участникам"
    )
    if not events:
        text += "\n\nПока нет завершённых мероприятий. Когда событие будет завершено, оно появится здесь"
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(ActivitySetupStates.lines)
async def create_finish_stable(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    event = await session.get(Event, int(data.get("activity_event_id", 0)))
    if not event:
        await state.clear()
        await message.answer("Мероприятие не найдено")
        return

    created = 0
    rejected = 0
    for raw_line in (message.text or "").splitlines():
        parts = [item.strip() for item in raw_line.split("|")]
        if len(parts) < 3:
            rejected += 1
            continue
        title = clean_text(parts[0], 255)
        try:
            points = int(parts[1])
        except ValueError:
            rejected += 1
            continue
        submission_type = (clean_text(parts[2], 32) or "").lower()
        description = clean_text(parts[3], 1000) if len(parts) > 3 else title
        if not title or submission_type not in ALLOWED_TYPES or not 0 <= points <= 1000:
            rejected += 1
            continue
        session.add(
            EventActivity(
                event_id=event.id,
                title=title,
                description=description or title,
                submission_type=submission_type,
                points=points,
                requires_review=True,
                deadline=datetime.now().astimezone() + timedelta(days=7),
                is_active=True,
            )
        )
        created += 1

    await state.clear()
    if not created:
        await message.answer("Не удалось создать активности. Проверьте формат: Название | баллы | тип | описание")
        return
    await message.answer(
        f"Создано активностей: {created}. Пропущено строк: {rejected}",
        reply_markup=_manage_keyboard(event.id),
    )


async def _submission_card(message: Message, session: AsyncSession, submission: EventActivitySubmission) -> None:
    activity = await session.get(EventActivity, submission.activity_id)
    participant = await session.get(User, submission.user_id)
    if not activity or not participant:
        return
    event = await session.get(Event, activity.event_id)
    status_label = {
        "pending": "на проверке у админа",
        "leader_approved": "проверено лидером, ждёт финального начисления",
    }.get(submission.status, submission.status)
    telegram = f"@{participant.username}" if participant.username else str(participant.telegram_id)
    await message.answer(
        "📥 Активность на проверку\n\n"
        f"Участник: {participant.first_name} {participant.last_name or ''}\n"
        f"Telegram: {telegram}\n"
        f"Мероприятие: {event.title if event else activity.event_id}\n"
        f"Активность: {activity.title}\n"
        f"Статус: {status_label}\n"
        f"Баллы: {activity.points}\n"
        f"Тип: {submission.file_type or activity.submission_type}\n\n"
        f"Подтверждение:\n{submission.text or 'прикреплён файл'}",
        reply_markup=_review_keyboard(submission.id),
    )
    await _send_file(message, submission)


@router.callback_query(F.data == "admin:event_activities:review")
async def review_list_stable(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    submissions = list(
        (
            await session.scalars(
                select(EventActivitySubmission)
                .where(EventActivitySubmission.status.in_(REVIEWABLE_ACTIVITY_STATUSES))
                .order_by(EventActivitySubmission.created_at)
                .limit(50)
            )
        ).all()
    )
    if not submissions:
        await call.message.answer("Активностей на проверке нет")
        return
    await call.message.answer(f"Активности на проверке: {len(submissions)}")
    for submission in submissions:
        await _submission_card(call.message, session, submission)


@router.callback_query(F.data.startswith("admin:activity:approve:"))
async def approve_stable(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    submission = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not submission or submission.status not in REVIEWABLE_ACTIVITY_STATUSES:
        await call.message.answer("Эта заявка уже проверена")
        return
    activity = await session.get(EventActivity, submission.activity_id)
    participant = await session.get(User, submission.user_id)
    if not activity or not participant:
        await call.message.answer("Активность или участник не найдены")
        return

    existing = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == participant.id,
            PointTransaction.related_event_id == activity.event_id,
            PointTransaction.reason.ilike(f"%{activity.title}%"),
            PointTransaction.points > 0,
        )
    )
    submission.status = "approved"
    submission.reviewed_by = user.id if user else None
    if existing or submission.points_awarded > 0:
        await call.message.answer("Заявка принята. Баллы за эту активность уже начислялись ранее")
        return

    submission.points_awarded = activity.points
    await add_points(
        session,
        user_id=participant.id,
        points=activity.points,
        reason=f"Активность после мероприятия: {activity.title}",
        approved_by=user.id if user else None,
        related_event_id=activity.event_id,
    )
    await safe_send(
        bot,
        participant.telegram_id,
        f"Активность «{activity.title}» одобрена. Начислено: +{activity.points} баллов",
    )
    await call.message.answer("Активность одобрена. Баллы начислены один раз")


@router.callback_query(F.data.startswith("admin:activity:reject:"))
async def reject_stable(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    submission = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not submission or submission.status not in REVIEWABLE_ACTIVITY_STATUSES:
        await call.message.answer("Эта заявка уже проверена")
        return
    activity = await session.get(EventActivity, submission.activity_id)
    participant = await session.get(User, submission.user_id)
    submission.status = "rejected"
    submission.reviewed_by = user.id if user else None
    if activity and participant:
        await safe_send(
            bot,
            participant.telegram_id,
            f"Активность «{activity.title}» отклонена. Баллы не начислены. Можно отправить подтверждение повторно",
        )
    await call.message.answer("Активность отклонена. Баллы не начислены")
