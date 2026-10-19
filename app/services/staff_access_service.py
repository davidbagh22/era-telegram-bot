"""Explicit global capabilities for community-wide operational queues."""
from sqlalchemy import select

from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.services.leadership_permission_service import has_scoped_permission
from app.utils.constants import ApplicationStatus


async def can_operate_queue(session, user, settings, permission):
    if user is None:
        return False
    actor = await session.scalar(select(User).where(User.id == user.id)
                                 .execution_options(populate_existing=True))
    if (actor is None or actor.is_blocked or actor.is_archived
            or actor.application_status != ApplicationStatus.APPROVED):
        return False
    if is_full_admin(actor, settings, actor.telegram_id):
        return True
    await session.refresh(actor, attribute_names=['permission_grants'])
    return await has_scoped_permission(session, actor, settings, actor.telegram_id, permission)
