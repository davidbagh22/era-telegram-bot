from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    Project,
    Task,
    User,
)
from app.keyboards.common import back_keyboard
from app.keyboards.participant import cabinet_keyboard
from app.repositories.users import rating, user_stats
from app.utils import texts
from app.utils.constants import (
    ApplicationStatus,
    PROJECT_STATUS_LABELS,
    REGISTRATION_STATUS_LABELS,
    TASK_STATUS_LABELS,
)
from app.utils.telegram import send_long_text

router = Router(name="cabinet")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


async def _rating_context(session: AsyncSession, user: User) -> tuple[list, int | str]:
    rows = await rating(session, limit=1000)
    place = next(
        (index for index, (item, _) in enumerate(rows, 1) if item.id == user.id), "—"
    )
    return rows, place


@router.callback_query(F.data == "cabinet:open")
async def cabinet(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(texts.CABINET, reply_markup=cabinet_keyboard())


@router.callback_query(F.data == "cabinet:profile")
async def profile(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    stats = await user_stats(session, user.id)
    await call.message.answer(
        texts.profile_text(user, stats), reply_markup=back_keyboard("cabinet:open")
    )


@router.callback_query(F.data == "cabinet:journey")
async def journey(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    stats = await user_stats(session, user.id)
    _, place = await _rating_context(session, user)
    await call.message.answer(
        texts.journey_text(user, stats, place),
        reply_markup=back_keyboard("cabinet:open"),
    )


@router.callback_query(F.data == "cabinet:points")
async def points(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    rows = (
        await session.scalars(
            select(PointTransaction)
            .where(PointTransaction.user_id == user.id)
            .order_by(desc(PointTransaction.created_at))
            .limit(10)
        )
    ).all()
    total = sum(
        item.points
        for item in (
            await session.scalars(
                select(PointTransaction).where(PointTransaction.user_id == user.id)
            )
        ).all()
    )
    await call.message.answer(
        texts.points_text(total, ((item.points, item.reason) for item in rows)),
        reply_markup=back_keyboard("cabinet:open"),
    )


@router.callback_query(F.data == "cabinet:rating")
async def show_rating(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    rows, place = await _rating_context(session, user)
    current_points = next((score for item, score in rows if item.id == user.id), 0)
    names = [
        (f"{item.first_name} {item.last_name or ''}".strip(), score)
        for item, score in rows[:10]
    ]
    await call.message.answer(
        texts.rating_text(names, place, current_points),
        reply_markup=back_keyboard("cabinet:open"),
    )


@router.callback_query(F.data == "cabinet:portfolio")
async def portfolio(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    items = (
        await session.scalars(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == user.id)
            .order_by(desc(PortfolioItem.created_at))
        )
    ).all()
    if not items:
        await call.message.answer(
            texts.PORTFOLIO_EMPTY, reply_markup=back_keyboard("cabinet:open")
        )
        return
    lines = "\n".join(
        f"• {item.title} — {item.description or item.item_type}" for item in items
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сформировать резюме ЭРА", callback_data="portfolio:resume"
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data="cabinet:open")],
        ]
    )
    await send_long_text(
        call.message, f"{texts.PORTFOLIO}\n\n{lines}", reply_markup=keyboard
    )


@router.callback_query(F.data == "portfolio:resume")
async def resume(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    items = (
        await session.scalars(
            select(PortfolioItem.title).where(PortfolioItem.user_id == user.id)
        )
    ).all()
    stats = await user_stats(session, user.id)
    await send_long_text(
        call.message,
        texts.portfolio_resume(user, items, stats),
        reply_markup=back_keyboard("cabinet:portfolio"),
    )


@router.callback_query(F.data == "cabinet:projects")
async def my_projects(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    projects = (
        await session.scalars(
            select(Project)
            .where(Project.author_id == user.id)
            .order_by(desc(Project.created_at))
        )
    ).all()
    body = (
        "\n".join(
            f"• {p.title} — {PROJECT_STATUS_LABELS.get(p.status, 'Статус уточняется')}"
            for p in projects
        )
        or "Проектов пока нет."
    )
    await call.message.answer(body, reply_markup=back_keyboard("cabinet:open"))


@router.callback_query(F.data == "cabinet:tasks")
async def my_tasks(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    tasks = (
        await session.scalars(
            select(Task).where(Task.assignee_id == user.id).order_by(Task.deadline)
        )
    ).all()
    body = (
        "\n".join(
            f"• {task.title} — {TASK_STATUS_LABELS.get(task.status, 'Статус уточняется')}, "
            f"до {task.deadline:%d.%m.%Y}"
            for task in tasks
        )
        or "Задач пока нет."
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for task in tasks:
        if task.status == "new":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Начать: {task.title[:35]}",
                        callback_data=f"task:start:{task.id}",
                    )
                ]
            )
        if task.status == "in_progress":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"На проверку: {task.title[:32]}",
                        callback_data=f"task:submit:{task.id}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="cabinet:open")])
    await call.message.answer(
        body, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.regexp(r"^task:(start|submit):\d+$"))
async def update_task(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    _, action, raw_id = call.data.split(":")
    task = await session.get(Task, int(raw_id))
    if task is None or task.assignee_id != user.id:
        await call.message.answer(texts.NO_ACCESS)
        return
    if action == "start" and task.status == "new":
        task.status = "in_progress"
        await call.message.answer("Задача отмечена как выполняемая.")
    elif action == "submit" and task.status == "in_progress":
        task.status = "review"
        await call.message.answer("Задача отправлена на проверку лидеру.")
    else:
        await call.message.answer("Статус задачи уже изменился.")


@router.callback_query(F.data == "cabinet:departments")
async def my_departments(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    departments = (
        "\n".join(f"• {item.department.name}" for item in user.departments)
        or "• Не выбраны"
    )
    directions = (
        "\n".join(f"• {item.direction.name}" for item in user.directions)
        or "• Не выбраны"
    )
    await call.message.answer(
        f"Мои департаменты\n{departments}\n\nМои направления\n{directions}",
        reply_markup=back_keyboard("cabinet:open"),
    )


@router.callback_query(F.data == "cabinet:events")
async def my_events(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
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
        await call.message.answer(
            "Регистраций на мероприятия пока нет.",
            reply_markup=back_keyboard("cabinet:open"),
        )
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard_rows = []
    lines = []
    for registration, event in rows:
        lines.append(
            f"• {event.title} — {event.event_date:%d.%m.%Y}, "
            f"{REGISTRATION_STATUS_LABELS.get(registration.status, 'Статус уточняется')}"
        )
        if event.selfie_required:
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Селфи: {event.title[:35]}",
                        callback_data=f"selfie:start:{event.id}",
                    )
                ]
            )
    keyboard_rows.append(
        [InlineKeyboardButton(text="Назад", callback_data="cabinet:open")]
    )
    await call.message.answer(
        "Мои мероприятия\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )
