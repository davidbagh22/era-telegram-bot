from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send
from app.utils import texts
from app.utils.constants import Role
from app.utils.validators import clean_text

router = Router(name="admin_projects_block5_team")


class TeamPostStates(StatesGroup):
    edit = State()
    reject = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(telegram_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


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


def _keyboard(project_id: int, prepared: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👁 Предпросмотр", callback_data=f"admin:team_post:preview:{project_id}")]]
    if prepared:
        rows.append([InlineKeyboardButton(text="📣 Опубликовать 2/2", callback_data=f"admin:team_post:publish:{project_id}")])
    else:
        rows.append([InlineKeyboardButton(text="✅ Одобрить 1/2", callback_data=f"admin:team_post:prepare:{project_id}")])
    rows.append([InlineKeyboardButton(text="✏️ Отредактировать", callback_data=f"admin:team_post:edit:{project_id}")])
    rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:team_post:reject:{project_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("admin:team_post:preview:"))
async def preview(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    text = (project.form_data or {}).get("team_search_post") if project else None
    if not project or not text:
        await call.message.answer("Публикация не найдена")
        return
    await call.message.answer(f"👁 Предпросмотр публикации\n\n🔍 Команда для проекта ЭРА\n\n{project.title}\n\n{text}", reply_markup=_keyboard(project.id))


@router.callback_query(F.data.startswith("admin:team_post:prepare:"))
async def prepare(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if not project:
        await call.message.answer("Проект не найден")
        return
    data = dict(project.form_data or {})
    data["team_search_status"] = "prepared"
    project.form_data = data
    await call.message.answer("Публикация подготовлена. Финальное нажатие отправит её в общий чат.", reply_markup=_keyboard(project.id, prepared=True))


@router.callback_query(F.data.startswith("admin:team_post:publish:"))
async def publish(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    data = dict(project.form_data or {}) if project else {}
    text = data.get("team_search_post")
    if not project or not text or data.get("team_search_status") != "prepared":
        await call.message.answer("Сначала нажмите «Одобрить 1/2»")
        return
    data["team_search_status"] = "published"
    project.form_data = data
    public_text = f"🔍 Команда для проекта ЭРА\n\n{project.title}\n\n{text}"
    if settings.general_chat_id:
        await safe_send(bot, settings.general_chat_id, public_text)
    author = await session.get(User, project.author_id)
    if author:
        await safe_send(bot, author.telegram_id, f"Публикация для поиска команды по проекту «{project.title}» одобрена.")
    await call.message.answer("Публикация отправлена в общий чат, если он подключён.")


@router.callback_query(F.data.startswith("admin:team_post:edit:"))
async def edit_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(TeamPostStates.edit)
    await state.update_data(team_project_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Отправьте новый текст публикации для поиска команды.")


@router.message(TeamPostStates.edit)
async def edit_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await _guard(message, user, settings):
        return
    text = clean_text(message.text or "", 2000)
    if len(text) < 30:
        await message.answer("Слишком коротко. Добавьте конкретику.")
        return
    data = await state.get_data()
    project = await session.get(Project, int(data["team_project_id"]))
    if not project:
        await state.clear()
        await message.answer("Проект не найден")
        return
    form_data = dict(project.form_data or {})
    form_data["team_search_post"] = text
    form_data["team_search_status"] = "edited"
    project.form_data = form_data
    await state.clear()
    await message.answer("Текст обновлён. Проверьте предпросмотр и подтвердите публикацию.", reply_markup=_keyboard(project.id))


@router.callback_query(F.data.startswith("admin:team_post:reject:"))
async def reject_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(TeamPostStates.reject)
    await state.update_data(team_project_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите причину отклонения публикации.")


@router.message(TeamPostStates.reject)
async def reject_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    reason = clean_text(message.text or "", 1000)
    if not reason:
        await message.answer("Причина обязательна")
        return
    data = await state.get_data()
    project = await session.get(Project, int(data["team_project_id"]))
    if not project:
        await state.clear()
        await message.answer("Проект не найден")
        return
    form_data = dict(project.form_data or {})
    form_data["team_search_status"] = "rejected"
    project.form_data = form_data
    author = await session.get(User, project.author_id)
    if author:
        await safe_send(bot, author.telegram_id, f"Публикация для поиска команды по проекту «{project.title}» отклонена.\n\nПричина: {reason}")
    await state.clear()
    await message.answer("Публикация отклонена. Автор уведомлён.")
