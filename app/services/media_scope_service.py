"""Area calendar delegation on the shared PermissionGrant, never a global role."""
from sqlalchemy import func, select

from app.database.models import AuditLog, Direction, PermissionGrant, User
from app.services import media_service
from app.services.audit_service import audit
from app.services.task_service import media_team_access

AREA_IDS = {"era": 1, "ksoors": 2}
PERMISSION = "media.calendar.manage"
ACTION = "media.calendar_scope_changed"


async def current_user(session, user):
    return await session.scalar(select(User).where(User.id == user.id).execution_options(populate_existing=True))


async def require_manager(session, user, settings):
    actor = await current_user(session, user)
    if not await media_service.can_manage_media(session, actor, settings):
        raise PermissionError("Назначать редакторов может только руководитель медиа или председатель")
    return actor


async def can_edit_calendar(session, user, settings, area):
    if area not in AREA_IDS or user is None:
        return False
    actor = await current_user(session, user)
    if await media_service.can_manage_media(session, actor, settings):
        return True
    if actor is None or not await media_team_access(session, actor):
        return False
    grant = await session.scalar(select(PermissionGrant).where(
        PermissionGrant.user_id == actor.id, PermissionGrant.permission == PERMISSION,
        PermissionGrant.scope_type == "media_area", PermissionGrant.scope_id == AREA_IDS[area],
        PermissionGrant.is_active.is_(True)))
    if grant is None:
        return False
    grantor = await session.scalar(select(User).where(User.id == grant.granted_by).execution_options(populate_existing=True))
    return await media_service.can_manage_media(session, grantor, settings)


async def revision(session, direction_id):
    return int(await session.scalar(select(func.max(AuditLog.id)).where(
        AuditLog.action == ACTION, AuditLog.entity_type == "direction", AuditLog.entity_id == direction_id)) or 0)


async def scope_state(session, user, settings, area):
    await require_manager(session, user, settings)
    direction = await session.scalar(select(Direction).where(Direction.name == "Медиа"))
    rows = (await session.scalars(select(PermissionGrant).where(
        PermissionGrant.permission == PERMISSION, PermissionGrant.scope_type == "media_area",
        PermissionGrant.scope_id == AREA_IDS[area], PermissionGrant.is_active.is_(True)))).all()
    result = []
    for grant in rows:
        target = await session.get(User, grant.user_id)
        if target and await can_edit_calendar(session, target, settings, area):
            result.append({"id": target.id, "name": f"{target.first_name} {target.last_name or ''}".strip()})
    return {"revision": await revision(session, direction.id) if direction else 0, "editors": result}


async def set_editor(session, user, settings, area, target_id, enabled, expected_revision):
    if area not in AREA_IDS:
        raise ValueError("Неизвестное направление")
    target = await session.scalar(select(User).where(User.id == target_id).with_for_update()
                                  .execution_options(populate_existing=True))
    direction = await session.scalar(select(Direction).where(Direction.name == "Медиа").with_for_update()
                                     .execution_options(populate_existing=True))
    actor = await require_manager(session, user, settings)
    if direction is None or target is None:
        raise ValueError("Участник медиаотдела не найден")
    if enabled and not await media_team_access(session, target):
        raise ValueError("Выберите действующего участника медиаотдела")
    grant = await session.scalar(select(PermissionGrant).where(
        PermissionGrant.user_id == target_id, PermissionGrant.permission == PERMISSION,
        PermissionGrant.scope_type == "media_area", PermissionGrant.scope_id == AREA_IDS[area])
        .with_for_update().execution_options(populate_existing=True))
    active = bool(grant and grant.is_active)
    valid_grantor = bool(grant and await media_service.can_manage_media(session,
        await session.get(User, grant.granted_by), settings))
    current_revision = await revision(session, direction.id)
    if current_revision != expected_revision:
        if active == enabled and (not enabled or valid_grantor):
            return await scope_state(session, actor, settings, area)
        raise ValueError("Полномочия уже изменены. Обновите список редакторов")
    if active == enabled and (not enabled or valid_grantor):
        return await scope_state(session, actor, settings, area)
    if grant is None:
        grant = PermissionGrant(user_id=target_id, permission=PERMISSION, scope_type="media_area",
                                scope_id=AREA_IDS[area], granted_by=actor.id, is_active=enabled)
        session.add(grant)
    else:
        grant.is_active = enabled
        grant.granted_by = actor.id
    await audit(session, actor_id=actor.id, action=ACTION, entity_type="direction", entity_id=direction.id,
                old_value={"area": area, "user_id": target_id, "enabled": active},
                new_value={"area": area, "user_id": target_id, "enabled": enabled})
    await session.flush()
    return await scope_state(session, actor, settings, area)


async def revoke_editor_grants(session, user_id, direction_id, *, actor_id=None, include_delegations=False):
    from sqlalchemy import or_
    condition = (PermissionGrant.user_id == user_id)
    if include_delegations:
        condition = or_(condition, PermissionGrant.granted_by == user_id)
    grants = (await session.scalars(select(PermissionGrant).where(
        condition, PermissionGrant.permission == PERMISSION, PermissionGrant.scope_type == "media_area",
        PermissionGrant.is_active.is_(True)).with_for_update())).all()
    if not grants:
        return
    for grant in grants:
        grant.is_active = False
    await audit(session, actor_id=actor_id, action=ACTION, entity_type="direction", entity_id=direction_id,
                new_value={"revoked_grants": [grant.id for grant in grants], "cause": "media_access_removed"})
    await session.flush()
