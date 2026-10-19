from io import BytesIO

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send, safe_send_document
from app.utils.deep_links import miniapp_admin_project_url


def _url_keyboard(text, url):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]]) if url else None


async def notify_project_reviewers(
    bot: Bot, settings: Settings, project: Project, user: User, document: str, *, session=None
) -> None:
    """Notify authorized private inboxes; the full file is never sent to a group."""
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    summary = (
        f"💡 Новый проект на рассмотрении\n\n{project.title}\n"
        f"Автор: {user.first_name} {user.last_name or ''} ({telegram})\n\n"
        "Полный файл проекта прикреплён ниже."
    )
    recipients = {int(i) for i in settings.admin_ids if int(i) > 0}
    if session is not None:
        from app.services.project_review_assignment_service import project_review_recipients
        recipients = await project_review_recipients(session, project, settings)
    keyboard = _url_keyboard(
        "Открыть модерацию",
        miniapp_admin_project_url(settings.effective_miniapp_url, project.id),
    )
    for chat_id in recipients:
        await safe_send(bot, chat_id, summary, reply_markup=keyboard)
        await safe_send_document(
            bot,
            chat_id,
            BufferedInputFile(
                BytesIO(document.encode("utf-8")).getvalue(),
                filename=f"ERA_project_{project.id}.txt",
            ),
            caption=f"Полный проект #{project.id}",
        )
