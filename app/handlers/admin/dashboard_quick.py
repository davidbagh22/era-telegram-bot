from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, Event, Project, TaskSubmission, User, UserBadge
from app.keyboards.admin import admin_panel_keyboard, admin_user_actions
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import ApplicationStatus, ProjectStatus, Role

router = Router(name="admin_dashboard_quick")


class DirectRewardStates(StatesGroup):
    points_amount = State()
    points_reason = State()
    badge_reason = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and any(g.is_active for g in (user.permission_grants or [])))
    )


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
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


async def _dashboard_text(session: AsyncSession) -> str:
    total_users = await session.scalar(select(func.count(User.id)).where(User.is_archived.is_(False))) or 0
    approved_users = await session.scalar(select(func.count(User.id)).where(User.application_status == ApplicationStatus.APPROVED, User.is_archived.is_(False))) or 0
    pending_users = await session.scalar(select(func.count(User.id)).where(User.application_status == ApplicationStatus.PENDING)) or 0
    projects_review = await session.scalar(select(func.count(Project.id)).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW]))) or 0
    projects_active = await session.scalar(select(func.count(Project.id)).where(Project.status.in_([ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS]))) or 0
    events_total = await session.scalar(select(func.count(Event.id))) or 0
    task_results = await session.scalar(select(func.count(TaskSubmission.id)).where(TaskSubmission.status == "pending")) or 0
    return (
        "⚙️ Админ-панель ЭРА\n\n"
        "Пульс организации:\n"
        f"👥 Участники всего: {total_users}\n"
        f"✅ Одобрены: {approved_users}\n"
        f"📝 Новые заявки: {pending_users}\n"
        f"💡 Проекты на проверке: {projects_review}\n"
        f"🚀 Активные проекты: {projects_active}\n"
        f"📅 Мероприятий в системе: {events_total}\n"
        f"📥 Итоги заданий на проверке: {task_results}\n\n"
        "Что ждёт внимания:\n"
        "👥 Участники — заявки, роли, статусы\n"
        "📅 События — мероприятия, регистрации, активности\n"
        "💬 Общение — вопросы и рассылки\n"
        "⭐ Развитие — баллы, знаки, возможности\n"
        "📊 Управление — аналитика, настройки, сервис"
    )


@router.message(F.text.in_({"⚙️ Управление", "/admin"}))
async def admin_dashboard_message(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(await _dashboard_text(session), reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(await _dashboard_text(session), reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:help")
async def admin_help(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "🧭 Что где находится\n\n"
        "👥 Участники — заявки, анкеты, роли, статусы, быстрые баллы и знаки\n"
        "📅 События — мероприятия, регистрация, посещаемость, задания после события\n"
        "💬 Общение — вопросы участников и рассылки\n"
        "⭐ Развитие — каталог возможностей, аукционы, знаки\n"
        "📊 Управление — аналитика, настройки и технические действия"
    )


@router.callback_query(F.data.startswith("admin:user:"))
async def user_card_direct(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    parts = call.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        return
    target = await session.get(User, int(parts[2]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    telegram = f"@{target.username}" if target.username else str(target.telegram_id)
    departments = ", ".join(x.department.name for x in target.departments) or "не выбраны"
    directions = ", ".join(x.direction.name for x in target.directions) or "не выбраны"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Дать баллы", callback_data=f"admin:user:points:{target.id}"),
                InlineKeyboardButton(text="🏅 Дать знак", callback_data=f"admin:user:badge:{target.id}"),
            ],
            *admin_user_actions(target.id).inline_keyboard,
        ]
    )
    await call.message.answer(
        f"👤 {target.first_name} {target.last_name or ''}\n\n"
        f"Возраст: {target.age or 'не указан'}\n"
        f"Город: {target.city or 'не указан'}\n"
        f"Телефон: {target.phone or 'не указан'}\n"
        f"Telegram: {telegram}\n"
        f"Email: {target.email or 'не указан'}\n\n"
        f"Департаменты: {departments}\n"
        f"Направления: {directions}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("admin:user:points:"))
async def direct_points_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(DirectRewardStates.points_amount)
    await state.update_data(target_user_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Сколько баллов начислить? Можно указать отрицательное число для списания.")


@router.message(DirectRewardStates.points_amount)
async def direct_points_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int((message.text or "").strip())
        if amount == 0 or abs(amount) > 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от -1000 до 1000, кроме нуля")
        return
    await state.update_data(points_amount=amount)
    await state.set_state(DirectRewardStates.points_reason)
    await message.answer("За что начисляем / списываем баллы?")


@router.message(DirectRewardStates.points_reason)
async def direct_points_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    reason = (message.text or "").strip()[:500]
    if not reason:
        await message.answer("Причина обязательна")
        return
    await add_points(
        session,
        user_id=int(data["target_user_id"]),
        points=int(data["points_amount"]),
        reason=reason,
        approved_by=user.id if user else None,
    )
    await state.clear()
    await message.answer("Баллы изменены")


@router.callback_query(F.data.startswith("admin:user:badge:"))
async def direct_badge_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    owned = set((await session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == target_id))).all())
    badges = (await session.scalars(select(Badge).where(~Badge.id.in_(owned or {-1})).order_by(Badge.id))).all()
    if not badges:
        await call.message.answer("У пользователя уже есть все доступные знаки")
        return
    await state.update_data(target_user_id=target_id)
    rows = [[InlineKeyboardButton(text=f"#{b.id} · {b.name}", callback_data=f"admin:user:badge_choose:{b.id}")] for b in badges]
    await call.message.answer("Какой знак вручить?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("admin:user:badge_choose:"))
async def direct_badge_choose(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.update_data(badge_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(DirectRewardStates.badge_reason)
    await call.message.answer("За что вручаем знак?")


@router.message(DirectRewardStates.badge_reason)
async def direct_badge_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    reason = (message.text or "").strip()[:500]
    if not reason:
        await message.answer("Причина обязательна")
        return
    session.add(
        UserBadge(
            user_id=int(data["target_user_id"]),
            badge_id=int(data["badge_id"]),
            reason=reason,
            awarded_by=user.id if user else None,
        )
    )
    await state.clear()
    await message.answer("Знак выдан")
