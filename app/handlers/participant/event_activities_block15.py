from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventActivitySubmission, EventRegistration, User
from app.services.notification_service import notify_admins
from app.utils import texts
from app.utils.constants import ApplicationStatus, RegistrationStatus
from app.utils.validators import clean_text

router = Router(name="participant_event_activities_block15")

ALLOWED_PROOF_TYPES = {"photo", "link", "text", "file", "manual"}
ACTIVE_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
    RegistrationStatus.ATTENDED,
}


class ActivityProofStates(StatesGroup):
    proof = State()


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _type_label(value: str) -> str:
    return {
        "photo": "фото",
        "link": "ссылка",
        "text": "текст",
        "file": "файл",
        "manual": "заявка без вложения",
    }.get(value, value)


def _activities_keyboard(activities: list[EventActivity]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Выполнить: {activity.title[:34]} · +{activity.points}",
                callback_data=f"activity:do:{activity.id}",
            )
        ]
        for activity in activities
    ]
    rows.append([InlineKeyboardButton(text="← К мероприятию", callback_data=f"event:view:{activities[0].event_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _registration(session: AsyncSession, event_id: int, user_id: int) -> EventRegistration | None:
    return await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
            EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )


async def _notify_proof(
    bot: Bot,
    settings: Settings,
    submission: EventActivitySubmission,
    activity: EventActivity,
    event: Event,
    user: User,
) -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить и начислить",
                    callback_data=f"admin:activity:approve:{submission.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"admin:activity:reject:{submission.id}",
                )
            ],
        ]
    )
    await notify_admins(
        bot,
        settings,
        "📥 Новая активность на проверку\n\n"
        f"Участник: {user.first_name} {user.last_name or ''}\n"
        f"Мероприятие: {event.title}\n"
        f"Активность: {activity.title}\n"
        f"Баллы: {activity.points}\n"
        f"Подтверждение: {submission.text or _type_label(submission.file_type or activity.submission_type)}",
        reply_markup=markup,
    )
    if not submission.file_id:
        return
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    for chat_id in recipients:
        try:
            if submission.file_type == "photo":
                await bot.send_photo(chat_id, submission.file_id, caption="Подтверждение активности")
            else:
                await bot.send_document(chat_id, submission.file_id, caption="Подтверждение активности")
        except Exception:
            continue


@router.callback_query(F.data.startswith("event:activities:"))
async def activities_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event_id = int(call.data.rsplit(":", 1)[-1])
    event = await session.get(Event, event_id)
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    if not await _registration(session, event.id, user.id):
        await call.message.answer("Активности доступны после регистрации на мероприятие.")
        return
    activities = list(
        (
            await session.scalars(
                select(EventActivity)
                .where(EventActivity.event_id == event.id, EventActivity.is_active.is_(True))
                .order_by(EventActivity.id)
            )
        ).all()
    )
    if not activities:
        await call.message.answer("Дополнительных активностей пока нет.")
        return
    lines = [
        f"• {item.title} — +{item.points}\n  {item.description}\n  Подтверждение: {_type_label(item.submission_type)}"
        for item in activities
    ]
    await call.message.answer(
        f"✨ Активности мероприятия\n\n{event.title}\n\n" + "\n\n".join(lines),
        reply_markup=_activities_keyboard(activities),
    )


@router.callback_query(F.data.startswith("activity:do:"))
@router.callback_query(F.data.startswith("activity:submit:"))
async def proof_start(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    activity = await session.get(EventActivity, int(call.data.rsplit(":", 1)[-1]))
    if not activity or not activity.is_active:
        await call.message.answer("Активность недоступна")
        return
    if not await _registration(session, activity.event_id, user.id):
        await call.message.answer("Активность доступна только зарегистрированным участникам.")
        return
    existing = await session.scalar(
        select(EventActivitySubmission).where(
            EventActivitySubmission.activity_id == activity.id,
            EventActivitySubmission.user_id == user.id,
        )
    )
    if existing and existing.status == "approved":
        await call.message.answer("Эта активность уже принята. Повторная отправка закрыта.")
        return
    if existing and existing.status == "pending":
        await call.message.answer("Ваш результат уже на проверке.")
        return
    proof_type = activity.submission_type if activity.submission_type in ALLOWED_PROOF_TYPES else "text"
    if proof_type == "manual":
        submission = existing or EventActivitySubmission(activity_id=activity.id, user_id=user.id)
        submission.text = "Заявка на ручную проверку"
        submission.file_id = None
        submission.file_type = "manual"
        submission.status = "pending"
        submission.reviewed_by = None
        submission.admin_comment = None
        if existing is None:
            session.add(submission)
        await session.flush()
        event = await session.get(Event, activity.event_id)
        await _notify_proof(bot, settings, submission, activity, event, user)
        await call.message.answer("Заявка отправлена на проверку.")
        return
    await state.set_state(ActivityProofStates.proof)
    await state.update_data(activity_id=activity.id, proof_type=proof_type)
    prompts = {
        "photo": "Отправьте фотографию.",
        "link": "Отправьте ссылку.",
        "text": "Отправьте текстовое подтверждение.",
        "file": "Отправьте документ или файл.",
    }
    await call.message.answer(
        f"✨ {activity.title}\n\n{activity.description}\n\n"
        f"Баллы: +{activity.points}\n{prompts[proof_type]}"
    )


@router.message(ActivityProofStates.proof)
async def proof_finish(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    activity = await session.get(EventActivity, int(data["activity_id"]))
    if not activity or not activity.is_active:
        await state.clear()
        await message.answer("Активность недоступна")
        return
    proof_type = data["proof_type"]
    text = clean_text(message.text or message.caption or "", 3000) or None
    file_id = None
    file_type = None
    if proof_type == "photo":
        if not message.photo:
            await message.answer("Нужно отправить именно фотографию.")
            return
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif proof_type == "link":
        if not text or not (text.startswith("http://") or text.startswith("https://") or text.startswith("t.me/")):
            await message.answer("Отправьте корректную ссылку.")
            return
        file_type = "link"
    elif proof_type == "text":
        if not text:
            await message.answer("Отправьте текстовое подтверждение.")
            return
        file_type = "text"
    elif proof_type == "file":
        if not message.document:
            await message.answer("Нужно отправить документ или файл.")
            return
        file_id = message.document.file_id
        file_type = "file"
    existing = await session.scalar(
        select(EventActivitySubmission).where(
            EventActivitySubmission.activity_id == activity.id,
            EventActivitySubmission.user_id == user.id,
        )
    )
    submission = existing or EventActivitySubmission(activity_id=activity.id, user_id=user.id)
    submission.text = text
    submission.file_id = file_id
    submission.file_type = file_type
    submission.status = "pending"
    submission.reviewed_by = None
    submission.admin_comment = None
    if existing is None:
        session.add(submission)
    await session.flush()
    event = await session.get(Event, activity.event_id)
    await _notify_proof(bot, settings, submission, activity, event, user)
    await state.clear()
    await message.answer("Результат отправлен на проверку. После решения Вы получите уведомление.")
