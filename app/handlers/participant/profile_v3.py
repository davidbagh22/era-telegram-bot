from __future__ import annotations

from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, PortfolioItem, User, UserBadge
from app.repositories.users import rating, user_stats
from app.services.notification_service import notify_admins
from app.services.resume_service import build_era_resume
from app.utils import texts
from app.utils.constants import ApplicationStatus, ROLE_LABELS
from app.utils.validators import clean_text

router = Router(name="participant_profile_v3")


class ProfilePhotoStates(StatesGroup):
    photo = State()


class RecommendationStates(StatesGroup):
    title = State()
    description = State()
    file = State()


def _keyboard(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if (
        user is None
        or user.application_status != ApplicationStatus.APPROVED
        or user.is_blocked
        or user.is_archived
    ):
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    return True


@router.callback_query(F.data == "cabinet:profile")
async def profile_home(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    stats = await user_stats(session, user.id)
    rows = await rating(session, limit=1000)
    place = next((i for i, (person, _) in enumerate(rows, 1) if person.id == user.id), "—")
    points = next((score for person, score in rows if person.id == user.id), 0)
    items = (
        await session.scalars(
            select(PortfolioItem)
            .where(
                PortfolioItem.user_id == user.id,
                PortfolioItem.status.in_(["verified", "pending"]),
                PortfolioItem.item_type != "profile_photo",
            )
            .order_by(desc(PortfolioItem.created_at))
        )
    ).all()
    badge_rows = (
        await session.execute(
            select(Badge, UserBadge)
            .join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.user_id == user.id)
            .order_by(UserBadge.created_at.desc())
        )
    ).all()
    achievements = [x for x in items if x.item_type != "recommendation_letter"]
    recommendations = [x for x in items if x.item_type == "recommendation_letter"]
    badge_text = ", ".join(badge.name for badge, _ in badge_rows[:5]) or "пока нет"
    role = ROLE_LABELS.get(user.role, str(user.role))
    await call.message.answer(
        f"👤 {user.first_name} {user.last_name or ''}\n\n"
        f"Роль: {role}\n"
        f"Город: {user.city or '—'}\n"
        f"Баллы: {points} · место в рейтинге: {place}\n\n"
        f"Достижения: {len(achievements)}\n"
        f"Рекомендации: {len(recommendations)}\n"
        f"Мероприятия: {stats.get('events', 0)} · проекты: {stats.get('projects', 0)}\n"
        f"Знаки: {badge_text}\n\n"
        "Здесь собраны Ваш путь, подтверждённые материалы и резюме ЭРА",
        reply_markup=_keyboard([
            [
                InlineKeyboardButton(text="🎓 Портфолио", callback_data="cabinet:portfolio"),
                InlineKeyboardButton(text="🏆 Рейтинг", callback_data="cabinet:rating"),
            ],
            [
                InlineKeyboardButton(text="🖼 Фото", callback_data="profile:photo"),
                InlineKeyboardButton(text="💌 Рекомендация", callback_data="profile:recommendation"),
            ],
            [InlineKeyboardButton(text="📄 Скачать резюме ЭРА", callback_data="portfolio:resume")],
            [InlineKeyboardButton(text="🏛 Департаменты", callback_data="profile:departments")],
            [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
        ]),
    )


@router.callback_query(F.data == "profile:departments")
async def profile_departments(
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    if not await _guard(call, user):
        return
    departments = ", ".join(
        item.department.name
        for item in (user.departments or [])
        if getattr(item, "department", None)
    ) or "пока не выбраны"
    directions = ", ".join(
        item.direction.name
        for item in (user.directions or [])
        if getattr(item, "direction", None)
    ) or "пока не выбраны"
    rows = []
    if settings.internal_department_chat_url:
        rows.append([InlineKeyboardButton(text="🌿 Чат внутренних связей", url=settings.internal_department_chat_url)])
    if settings.external_department_chat_url:
        rows.append([InlineKeyboardButton(text="🌍 Чат внешних связей", url=settings.external_department_chat_url)])
    rows.append([InlineKeyboardButton(text="➕ Выбрать направление", callback_data="department:apply:start")])
    rows.append([InlineKeyboardButton(text="← Мой профиль", callback_data="cabinet:profile")])
    await call.message.answer(
        f"🏛 Мои департаменты и направления\n\n"
        f"Департаменты: {departments}\n"
        f"Направления: {directions}\n\n"
        "Можно перейти в чат или подать заявку на новое направление",
        reply_markup=_keyboard(rows),
    )


@router.callback_query(F.data == "profile:photo")
async def profile_photo_start(
    call: CallbackQuery, user: User | None, state: FSMContext
) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(ProfilePhotoStates.photo)
    await call.message.answer(
        "Отправьте фотографию для резюме\n\nЛучше вертикальный портрет без сильных фильтров",
        reply_markup=_keyboard([[InlineKeyboardButton(text="Отмена", callback_data="cabinet:profile")]]),
    )


@router.message(ProfilePhotoStates.photo, F.photo)
async def profile_photo_save(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    current = await session.scalar(
        select(PortfolioItem).where(
            PortfolioItem.user_id == user.id,
            PortfolioItem.item_type == "profile_photo",
        )
    )
    file_id = message.photo[-1].file_id
    if current:
        current.file_id = file_id
        current.status = "verified"
        current.title = "Фото для резюме"
    else:
        session.add(
            PortfolioItem(
                user_id=user.id,
                title="Фото для резюме",
                item_type="profile_photo",
                file_id=file_id,
                status="verified",
                submitted_by=user.id,
                verified_by=user.id,
            )
        )
    await state.clear()
    await message.answer(
        "Фото сохранено и будет добавлено в следующее резюме",
        reply_markup=_keyboard([[InlineKeyboardButton(text="← Мой профиль", callback_data="cabinet:profile")]]),
    )


@router.message(ProfilePhotoStates.photo)
async def profile_photo_wrong(message: Message) -> None:
    await message.answer("Пришлите фотографию как изображение")


@router.callback_query(F.data == "profile:recommendation")
async def recommendation_start(
    call: CallbackQuery, user: User | None, state: FSMContext
) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(RecommendationStates.title)
    await call.message.answer(
        "Кто выдал рекомендательное письмо?\n\nНапример: «Рекомендация от организации N»",
        reply_markup=_keyboard([[InlineKeyboardButton(text="Отмена", callback_data="cabinet:profile")]]),
    )


@router.message(RecommendationStates.title)
async def recommendation_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer("Напишите короткое название")
        return
    await state.update_data(recommendation_title=value)
    await state.set_state(RecommendationStates.description)
    await message.answer("Добавьте короткое пояснение или отправьте — чтобы пропустить")


@router.message(RecommendationStates.description)
async def recommendation_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1000)
    await state.update_data(
        recommendation_description=None if value in {"", "—", "-"} else value
    )
    await state.set_state(RecommendationStates.file)
    await message.answer("Прикрепите рекомендательное письмо файлом или фотографией")


@router.message(RecommendationStates.file, F.document | F.photo)
async def recommendation_file(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    file_id = message.document.file_id if message.document else message.photo[-1].file_id
    item = PortfolioItem(
        user_id=user.id,
        title=data["recommendation_title"],
        item_type="recommendation_letter",
        description=data.get("recommendation_description"),
        file_id=file_id,
        status="pending",
        submitted_by=user.id,
    )
    session.add(item)
    await session.flush()
    await state.clear()
    await message.answer(
        "Рекомендательное письмо отправлено на проверку. После подтверждения оно появится в портфолио и резюме",
        reply_markup=_keyboard([[InlineKeyboardButton(text="← Мой профиль", callback_data="cabinet:profile")]]),
    )
    await notify_admins(
        bot,
        settings,
        f"💌 Рекомендательное письмо на проверку #{item.id}\n\n"
        f"Участник: {user.first_name} {user.last_name or ''}\n"
        f"Название: {item.title}",
    )


@router.message(RecommendationStates.file)
async def recommendation_wrong(message: Message) -> None:
    await message.answer("Прикрепите файл или фотографию")


@router.callback_query(F.data == "portfolio:resume")
async def improved_resume(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user):
        return
    items = (
        await session.scalars(
            select(PortfolioItem).where(
                PortfolioItem.user_id == user.id,
                PortfolioItem.status == "verified",
                PortfolioItem.item_type != "profile_photo",
            )
        )
    ).all()
    photo = await session.scalar(
        select(PortfolioItem).where(
            PortfolioItem.user_id == user.id,
            PortfolioItem.item_type == "profile_photo",
            PortfolioItem.status == "verified",
        )
    )
    photo_bytes = None
    if photo and photo.file_id:
        try:
            destination = BytesIO()
            await bot.download(photo.file_id, destination=destination)
            photo_bytes = destination.getvalue()
        except TelegramAPIError:
            photo_bytes = None
    stats = await user_stats(session, user.id)
    try:
        content = build_era_resume(user, items, stats, photo_bytes=photo_bytes)
    except RuntimeError:
        await call.message.answer("Не удалось собрать PDF прямо сейчас. Попробуйте немного позже")
        return
    await call.message.answer_document(
        BufferedInputFile(content, filename=f"ERA_resume_{user.id}.pdf"),
        caption="Ваше обновлённое резюме ЭРА готово",
        reply_markup=_keyboard([[InlineKeyboardButton(text="← Мой профиль", callback_data="cabinet:profile")]]),
    )
