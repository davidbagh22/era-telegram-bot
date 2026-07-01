from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_project_team_review")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and any(g.is_active for g in (user.permission_grants or [])))
    )


async def _guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not _is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


@router.callback_query(F.data.regexp(r"^admin:team_post:(approve|reject):\d+$"))
async def team_post_review(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_project_id = call.data.split(":")
    project = await session.get(Project, int(raw_project_id))
    if not project:
        await call.message.answer("Проект не найден")
        return
    author = await session.get(User, project.author_id)
    form_data = dict(project.form_data or {})
    text = form_data.get("team_search_post")
    if not text:
        await call.message.answer("Текст публикации не найден")
        return
    if action == "reject":
        form_data["team_search_status"] = "rejected"
        project.form_data = form_data
        if author:
            await safe_send(bot, author.telegram_id, f"Публикация для поиска команды по проекту «{project.title}» отклонена. Подготовьте новый текст и отправьте снова.")
        await call.message.answer("Публикация отклонена")
        return
    form_data["team_search_status"] = "approved"
    project.form_data = form_data
    public_text = f"🔍 Команда для проекта ЭРА\n\n{project.title}\n\n{text}"
    if settings.general_chat_id:
        await safe_send(bot, settings.general_chat_id, public_text)
    if author:
        await safe_send(bot, author.telegram_id, f"Публикация для поиска команды по проекту «{project.title}» одобрена.")
    await call.message.answer("Публикация одобрена и отправлена в общий чат, если он подключён.")
