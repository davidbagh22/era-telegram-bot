from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventActivity, EventActivitySubmission, EventRegistration, User
from app.keyboards.common import back_keyboard
from app.utils import texts
from app.utils.constants import (
    ApplicationStatus,
    EVENT_STATUS_LABELS,
    REGISTRATION_STATUS_LABELS,
    EventStatus,
    RegistrationStatus,
)

router = Router(name="event_plans_changed")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    return True


def _can_change_plans(registration: EventRegistration, event: Event) -> bool:
    return registration.status in {RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME} and event.status not in {
        EventStatus.COMPLETED,
        EventStatus.CANCELLED,
        EventStatus.REPORT_SUBMITTED,
    }


@router.callback_query(F.data == "cabinet:events")
async def my_events(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return

    rows = (
        await session.execute(
            select(EventRegistration, Event)
            .join(Event, Event.id == EventRegistration.event_id)
            .where(EventRegistration.user_id == user.id)
            .order_by(desc(Event.event_date))
        )
    ).all()

    if not rows:
        await call.message.answer("Регистраций на мероприятия пока нет.", reply_markup=back_keyboard("cabinet:open"))
        return

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    lines: list[str] = []

    for registration, event in rows:
        lines.append(
            f"• {event.title} — {event.event_date:%d.%m.%Y}, "
            f"{REGISTRATION_STATUS_LABELS.get(registration.status, 'Статус уточняется')}"
        )
        lines.append(f"  Статус мероприятия: {EVENT_STATUS_LABELS.get(event.status, 'Уточняется')}")

        if _can_change_plans(registration, event):
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Планы изменились · {event.title[:28]}",
                        callback_data=f"event:plans_changed:{event.id}",
                    )
                ]
            )

        if registration.status not in {RegistrationStatus.NOT_COMING, RegistrationStatus.CANCELLED, RegistrationStatus.NO_SHOW}:
            activities = (
                await session.scalars(
                    select(EventActivity).where(
                        EventActivity.event_id == event.id,
                        EventActivity.is_active.is_(True),
                    )
                )
            ).all()
            submitted = set(
                (
                    await session.scalars(
                        select(EventActivitySubmission.activity_id).where(
                            EventActivitySubmission.user_id == user.id,
                            EventActivitySubmission.activity_id.in_([activity.id for activity in activities] or [-1]),
                            EventActivitySubmission.status.in_(["pending", "approved"]),
                        )
                    )
                ).all()
            )
            for activity in activities:
                if activity.id not in submitted:
                    keyboard_rows.append(
                        [
                            InlineKeyboardButton(
                                text=f"+{activity.points} · {activity.title[:30]}",
                                callback_data=f"event:activity:{activity.id}",
                            )
                        ]
                    )

    keyboard_rows.append([InlineKeyboardButton(text="Назад", callback_data="cabinet:open")])
    await call.message.answer(
        "Мои мероприятия\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )


@router.callback_query(F.data.startswith("event:plans_changed:"))
async def plans_changed(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return

    event_id = int(call.data.rsplit(":", 1)[-1])
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user.id,
        )
    )
    event = await session.get(Event, event_id)

    if registration is None or event is None:
        await call.message.answer("Регистрация на мероприятие не найдена.", reply_markup=back_keyboard("cabinet:events"))
        return

    if not _can_change_plans(registration, event):
        await call.message.answer(
            "Статус этой регистрации уже нельзя изменить через бот.",
            reply_markup=back_keyboard("cabinet:events"),
        )
        return

    registration.status = RegistrationStatus.NOT_COMING
    await call.message.answer(
        f"Поняли. Отметили, что вы не сможете прийти на «{event.title}».\n\nСпасибо, что сообщили заранее.",
        reply_markup=back_keyboard("cabinet:events"),
    )
