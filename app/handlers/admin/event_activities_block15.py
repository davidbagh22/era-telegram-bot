from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventActivitySubmission, PointTransaction, User
from app.handlers.admin.events_block6 import guard
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils.validators import clean_text

router = Router(name="admin_event_activities_block15")
ALLOWED_TYPES = {"photo", "link", "text", "file", "manual"}


class ActivitySetupStates(StatesGroup):
    lines = State()


def _review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить и начислить баллы",
                    callback_data=f"admin:activity:approve:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"admin:activity:reject:{submission_id}",
                )
            ],
        ]
    )


def _manage_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить активности",
                    callback_data=f"admin:event:activities:create:{event_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Отправить участникам",
                    callback_data=f"admin:event:activities:send:{event_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 На проверке",
                    callback_data="admin:event_activities:review",
                )
            ],
            [InlineKeyboardButton(text="← Мероприятия", callback_data="admin:events")],
        ]
    )


@router.callback_query(F.data.startswith("admin:event:activities:create:"))
async def create_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    await state.set_state(ActivitySetupStates.lines)
    await state.update_data(activity_event_id=event.id)
    await call.message.answer(
        "Отправьте активности списком. Одна строка — одна активность.\n\n"
        "Формат:\nНазвание | баллы | тип | описание\n\n"
        "Типы: photo, link, text, file, manual\n\n"
        "Пример:\n"
        "Выложить сторис | 30 | link | Отправьте ссылку на публикацию\n"
        "Помочь на регистрации | 40 | manual | Проверка организатором"
    )


@router.message(ActivitySetupStates.lines)
async def create_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await guard(message, user, settings):
        return
    data = await state.get_data()
    event = await session.get(Event, int(data["activity_event_id"]))
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
        proof_type = (clean_text(parts[2], 32) or "").lower()
        description = clean_text(parts[3], 1000) if len(parts) > 3 else title
        if not title or proof_type not in ALLOWED_TYPES or points < 0 or points > 1000:
            rejected += 1
            continue
        session.add(
            EventActivity(
                event_id=event.id,
                title=title,
                description=description or title,
                submission_type=proof_type,
                points=points,
                requires_review=True,
                deadline=datetime.now().astimezone() + timedelta(days=7),
                is_active=True,
            )
        )
        created += 1
    await state.clear()
    if not created:
        await message.answer("Не удалось создать активности. Проверьте формат и тип подтверждения.")
        return
    await message.answer(
        f"Создано активностей: {created}. Пропущено строк: {rejected}.",
        reply_markup=_manage_keyboard(event.id),
    )


async def _submission_card(message: Message, session: AsyncSession, submission: EventActivitySubmission) -> None:
    activity = await session.get(EventActivity, submission.activity_id)
    participant = await session.get(User, submission.user_id)
    if not activity or not participant:
        return
    event = await session.get(Event, activity.event_id)
    await message.answer(
        "📥 Активность на проверку\n\n"
        f"Участник: {participant.first_name} {participant.last_name or ''}\n"
        f"Мероприятие: {event.title if event else activity.event_id}\n"
        f"Активность: {activity.title}\n"
        f"Баллы: {activity.points}\n"
        f"Тип: {submission.file_type or activity.submission_type}\n"
        f"Подтверждение: {submission.text or 'прикреплён файл'}",
        reply_markup=_review_keyboard(submission.id),
    )
    if submission.file_id:
        try:
            if submission.file_type == "photo":
                await message.answer_photo(submission.file_id, caption="Подтверждение активности")
            else:
                await message.answer_document(submission.file_id, caption="Подтверждение активности")
        except Exception:
            await message.answer("Файл сохранён, но Telegram не смог открыть его повторно.")


@router.callback_query(F.data == "admin:event_activities:review")
async def review_list(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await guard(call, user, settings):
        return
    submissions = list(
        (
            await session.scalars(
                select(EventActivitySubmission)
                .where(EventActivitySubmission.status == "pending")
                .order_by(EventActivitySubmission.created_at)
                .limit(50)
            )
        ).all()
    )
    if not submissions:
        await call.message.answer("Активностей на проверке нет.")
        return
    await call.message.answer(f"Активности на проверке: {len(submissions)}")
    for submission in submissions:
        await _submission_card(call.message, session, submission)


@router.callback_query(F.data.startswith("admin:activity:approve:"))
async def approve(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await guard(call, user, settings):
        return
    submission = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not submission or submission.status != "pending":
        await call.message.answer("Эта заявка уже проверена.")
        return
    activity = await session.get(EventActivity, submission.activity_id)
    participant = await session.get(User, submission.user_id)
    if not activity or not participant:
        await call.message.answer("Активность или участник не найдены.")
        return
    existing = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == participant.id,
            PointTransaction.related_event_id == activity.event_id,
            PointTransaction.reason == f"Активность мероприятия: {activity.title}",
        )
    )
    submission.status = "approved"
    submission.reviewed_by = user.id if user else None
    if existing or submission.points_awarded > 0:
        await call.message.answer("Заявка принята. Баллы уже начислялись ранее.")
        return
    submission.points_awarded = activity.points
    await add_points(
        session,
        user_id=participant.id,
        points=activity.points,
        reason=f"Активность мероприятия: {activity.title}",
        approved_by=user.id if user else None,
        related_event_id=activity.event_id,
    )
    await safe_send(
        bot,
        participant.telegram_id,
        f"Активность «{activity.title}» одобрена. Начислено: +{activity.points} баллов.",
    )
    await call.message.answer("Активность одобрена. Баллы начислены один раз.")


@router.callback_query(F.data.startswith("admin:activity:reject:"))
async def reject(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await guard(call, user, settings):
        return
    submission = await session.get(EventActivitySubmission, int(call.data.rsplit(":", 1)[-1]))
    if not submission or submission.status != "pending":
        await call.message.answer("Эта заявка уже проверена.")
        return
    activity = await session.get(EventActivity, submission.activity_id)
    participant = await session.get(User, submission.user_id)
    submission.status = "rejected"
    submission.reviewed_by = user.id if user else None
    if activity and participant:
        await safe_send(
            bot,
            participant.telegram_id,
            f"Активность «{activity.title}» отклонена. Баллы не начислены. Можно отправить подтверждение повторно.",
        )
    await call.message.answer("Активность отклонена. Баллы не начислены.")
