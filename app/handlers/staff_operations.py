"""Private entry points for explicitly delegated capabilities."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services.project_workspace_service import can_review_any_projects
from app.services.staff_access_service import can_operate_queue

router = Router(name='staff_operations')


async def show_operations(message, session, user, settings):
    entries = []
    if await can_review_any_projects(session, user, settings):
        entries.append('/projects_review — проекты на проверке')
    for permission, label in (
        ('applications.review', '/applications_review — заявки участников'),
        ('support.manage', '/support_admin — обращения'),
        ('literature.manage', '/literature_admin — литературная редакция'),
        ('portfolio.review', '/issue_certificate — выдача сертификатов'),
    ):
        if await can_operate_queue(session, user, settings, permission):
            entries.append(label)
    await message.answer('Рабочие разделы\n\n' + ('\n'.join(entries) if entries else
                         'У вас нет назначенных прав для этих очередей.'))


@router.message(Command('staff'))
async def staff_command(message: Message, session: AsyncSession, user: User | None, settings: Settings):
    await show_operations(message, session, user, settings)


@router.callback_query(F.data == 'staff:home')
async def staff_home(call: CallbackQuery, session: AsyncSession, user: User | None, settings: Settings):
    await call.answer()
    await show_operations(call.message, session, user, settings)
