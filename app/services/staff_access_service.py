"""Explicit global capabilities for community-wide operational queues."""
from sqlalchemy import select

from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.services.leadership_permission_service import has_scoped_permission
from app.utils.constants import ApplicationStatus


# Stable numeric scopes because PermissionGrant.scope_id is an integer. These
# ids are part of the authorization contract; do not derive them from labels.
SUPPORT_CATEGORY_SCOPE = {
    "general": 1,
    "events": 2,
    "projects": 3,
    "points": 4,
    "access": 5,
}
LITERATURE_CATEGORY_SCOPE_ID = 1


def support_category_scope_id(category):
    return SUPPORT_CATEGORY_SCOPE.get(category)


async def can_operate_queue(session, user, settings, permission, *, telegram_id=None,
                            scope_type=None, scope_id=None):
    if user is None:
        return telegram_id in settings.admin_ids if telegram_id is not None else False
    actor = await session.scalar(select(User).where(User.id == user.id)
                                 .execution_options(populate_existing=True))
    if actor is None or actor.is_blocked or actor.is_archived:
        return False
    if is_full_admin(actor, settings, actor.telegram_id):
        return True
    if actor.application_status != ApplicationStatus.APPROVED:
        return False
    if permission == 'support.manage':
        from app.services.feature_flags import Feature, feature_enabled
        if not feature_enabled(settings, Feature.SUPPORT_THREADS, actor.telegram_id):
            return False
    await session.refresh(actor, attribute_names=['permission_grants'])
    if permission == 'support.manage' and scope_type is None:
        # Category-scoped support grants open the inbox entry point, but not a
        # global support operation. Object checks below always supply scope.
        if any(grant.is_active and grant.permission == permission
               and grant.scope_type == 'support_category'
               and grant.scope_id in SUPPORT_CATEGORY_SCOPE.values()
               for grant in actor.permission_grants or []):
            return True
    if permission == 'literature.manage' and scope_type is None:
        if any(grant.is_active and grant.permission == permission
               and grant.scope_type == 'literature_category'
               and grant.scope_id == LITERATURE_CATEGORY_SCOPE_ID
               for grant in actor.permission_grants or []):
            return True
    return await has_scoped_permission(session, actor, settings, actor.telegram_id, permission,
                                       scope_type=scope_type, scope_id=scope_id)


async def can_operate_support_category(session, user, settings, category, *, telegram_id=None):
    scope_id = support_category_scope_id(category)
    if scope_id is None:
        return False
    return await can_operate_queue(session, user, settings, 'support.manage',
        telegram_id=telegram_id, scope_type='support_category', scope_id=scope_id)


async def can_edit_literature(session, user, settings, *, telegram_id=None):
    return await can_operate_queue(session, user, settings, 'literature.manage',
        telegram_id=telegram_id, scope_type='literature_category',
        scope_id=LITERATURE_CATEGORY_SCOPE_ID)


async def can_manage_literature_settings(session, user, settings, *, telegram_id=None):
    return await can_operate_queue(session, user, settings, 'literature.manage',
        telegram_id=telegram_id, scope_type='global', scope_id=0)


async def allowed_support_categories(session, user, settings, *, telegram_id=None):
    if await can_operate_queue(session, user, settings, 'support.manage', telegram_id=telegram_id,
                               scope_type='global', scope_id=0):
        return set(SUPPORT_CATEGORY_SCOPE)
    return {category for category, scope_id in SUPPORT_CATEGORY_SCOPE.items()
            if await can_operate_support_category(session, user, settings, category,
                                                  telegram_id=telegram_id)}
