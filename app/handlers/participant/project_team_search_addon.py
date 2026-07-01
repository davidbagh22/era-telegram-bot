from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import notify_admins
from app.utils import texts
from app.utils.constants import ApplicationStatus, ProjectStatus

router = Router(name="participant_project_team_search_addon")


class ProjectTeamSearchStates(StatesGroup):
    text = State()


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def _load_owned_project(session: AsyncSession, project_id: int, user: User) -> Project | None:
    project = await session.get(Project, project_id)
    return project if project and project.author_id == user.id else None


@router.callback_query(F.data.startswith("project:team_post:"))
async def project_team_post_start(call: CallbackQuery, session: AsyncSession, user: User | None, state: FSMContext) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    project = await _load_owned_project(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Искать команду можно после одобрения проекта")
        return
    await state.set_state(ProjectTeamSearchStates.text)
    await state.update_data(team_project_id=project.id)
    await call.message.answer(
        "Напишите публикацию для поиска единомышленников.\n\n"
        "Структура:\n"
        "1. Кого ищем\n"
        "2. Что нужно сделать\n"
        "3. Сколько времени займёт участие\n"
        "4. Почему это стоит сделать\n\n"
        "Текст уйдёт админу на утверждение."
    )


@router.message(ProjectTeamSearchStates.text)
async def project_team_post_submit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    project = await _load_owned_project(session, int(data["team_project_id"]), user)
    if not project:
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    text = (message.text or message.caption or "").strip()
    if len(text) < 30:
        await message.answer("Слишком коротко. Добавьте, кого ищете и что нужно делать.")
        return
    form_data = dict(project.form_data or {})
    form_data["team_search_post"] = text
    form_data["team_search_status"] = "pending"
    project.form_data = form_data
    await state.clear()
    await message.answer("Публикация для поиска команды отправлена админу на утверждение.")
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    await notify_admins(
        bot,
        settings,
        f"🔍 Запрос на поиск команды\n\nПроект: {project.title}\nАвтор: {user.first_name} {user.last_name or ''} ({telegram})\n\n{text}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить публикацию", callback_data=f"admin:team_post:approve:{project.id}")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:team_post:reject:{project.id}")],
            ]
        ),
    )
