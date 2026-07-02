from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    PointTransaction,
    PortfolioItem,
    Task,
    User,
)
from app.keyboards.common import back_keyboard
from app.keyboards.participant import (
    journey_keyboard,
    portfolio_keyboard,
)
from app.repositories.users import rating, user_stats
from app.services.resume_service import build_era_resume
from app.utils import texts
from app.utils.constants import (
    ApplicationStatus,
)
from app.utils.telegram import send_long_text

router = Router(name="cabinet")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


async def _rating_context(session: AsyncSession, user: User) -> tuple[list, int | str]:
    rows = await rating(session, limit=1000)
    place = next(
        (index for index, (item, _) in enumerate(rows, 1) if item.id == user.id), "—"
    )
    return rows, place


async def _send_journey(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    stats = await user_stats(session, user.id)
    _, place = await _rating_context(session, user)
    await message.answer(
        texts.journey_text(user, stats, place),
        reply_markup=journey_keyboard(
            settings.internal_department_chat_url,
            settings.external_department_chat_url,
        ),
    )


async def _send_rating(message: Message, user: User, session: AsyncSession) -> None:
    rows, place = await _rating_context(session, user)
    current_points = next((score for item, score in rows if item.id == user.id), 0)
    names = [
        (f"{item.first_name} {item.last_name or ''}".strip(), score)
        for item, score in rows[:10]
    ]
    await message.answer(
        texts.rating_text(names, place, current_points),
        reply_markup=back_keyboard("menu:main"),
    )


@router.callback_query(F.data == "cabinet:open")
async def cabinet(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _guard(call, user):
        return
    await _send_journey(call.message, user, session, settings)


@router.message(F.text == "🌱 Мой путь")
@router.message(Command("journey"), F.chat.type == "private")
async def journey_button(
    message: Message,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await state.clear()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await message.answer(texts.APPLICATION_PENDING)
        return
    if user.is_blocked or user.is_archived:
        await message.answer(texts.BLOCKED)
        return
    await _send_journey(message, user, session, settings)


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
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _guard(call, user):
        return
    await _send_journey(call.message, user, session, settings)


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
    await _send_rating(call.message, user, session)


@router.message(F.text == "🏆 Рейтинг")
@router.message(Command("rating"), F.chat.type == "private")
async def rating_button(
    message: Message, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await _send_rating(message, user, session)


@router.callback_query(F.data == "cabinet:portfolio")
async def portfolio(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    items = (
        await session.scalars(
            select(PortfolioItem)
            .where(
                PortfolioItem.user_id == user.id,
                PortfolioItem.status.in_(["verified", "pending"]),
            )
            .order_by(desc(PortfolioItem.created_at))
        )
    ).all()
    if not items:
        await call.message.answer(
            texts.PORTFOLIO_EMPTY, reply_markup=portfolio_keyboard()
        )
        return
    lines = "\n".join(
        f"• {item.title} — {item.description or item.item_type}"
        + (" · на проверке" if item.status == "pending" else "")
        for item in items
    )
    await send_long_text(
        call.message,
        f"{texts.PORTFOLIO}\n\n{lines}",
        reply_markup=portfolio_keyboard(items),
    )


@router.callback_query(F.data.startswith("portfolio:file:"))
async def portfolio_file(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    item = await session.get(PortfolioItem, int(call.data.rsplit(":", 1)[-1]))
    if (
        item is None
        or item.user_id != user.id
        or item.status != "verified"
        or not item.file_id
    ):
        await call.message.answer("Файл недоступен")
        return
    try:
        await call.message.answer_document(item.file_id, caption=item.title)
    except TelegramAPIError:
        await call.message.answer_photo(item.file_id, caption=item.title)


@router.callback_query(F.data == "portfolio:resume")
async def resume(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    items = (
        await session.scalars(
            select(PortfolioItem).where(
                PortfolioItem.user_id == user.id,
                PortfolioItem.status == "verified",
            )
        )
    ).all()
    stats = await user_stats(session, user.id)
    try:
        content = build_era_resume(user, items, stats)
    except RuntimeError:
        await call.message.answer(
            "Не удалось собрать PDF прямо сейчас. Попробуйте ещё раз немного позже",
            reply_markup=back_keyboard("cabinet:portfolio"),
        )
        return
    await call.message.answer_document(
        BufferedInputFile(content, filename=f"ERA_resume_{user.id}.pdf"),
        caption="Ваше резюме ЭРА готово — его можно сохранить и отправить партнёрам или организаторам",
        reply_markup=back_keyboard("cabinet:portfolio"),
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
