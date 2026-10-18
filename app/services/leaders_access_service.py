"""Workcenter permissions use existing roles, appointments and scoped grants."""
from sqlalchemy import inspect, or_, select

from app.database.models import Department, Direction, User, UserDepartment, UserDirection
from app.services.authorization_service import is_full_admin
from app.services.leadership_permission_service import active_office_assignments, effective_scoped_permissions
from app.utils.constants import ApplicationStatus, Role

EXECUTIVE_OFFICES = {'Председатель', 'Заместитель председателя'}


def active(user):
    return bool(user and not user.is_archived and not user.is_blocked)


async def executive(session, user, settings):
    if not active(user):
        return False
    if is_full_admin(user, settings, user.telegram_id):
        return True
    return any(o.title in EXECUTIVE_OFFICES and o.scope_type == 'global'
               for _, o in await active_office_assignments(session, user.id))


async def scopes(session, user, settings, permission='tasks.manage'):
    if not active(user):
        return set()
    if await executive(session, user, settings):
        return {('global', 0)}
    state = inspect(user, raiseerr=False)
    if state is not None and 'permission_grants' in state.unloaded:
        await session.refresh(user, attribute_names=['permission_grants'])
    result = {(p.scope_type, p.scope_id) for p in await effective_scoped_permissions(session, user)
              if p.permission == permission and
              ((p.scope_type == 'global' and p.scope_id == 0) or
               (p.scope_type in {'department', 'direction'} and isinstance(p.scope_id, int) and p.scope_id > 0))}
    # A HEAD is bounded by actual memberships, never by the role name alone.
    if user.role == Role.HEAD:
        result.update(('department', ident) for ident in (await session.scalars(select(UserDepartment.department_id).where(UserDepartment.user_id==user.id))).all())
        result.update(('direction', ident) for ident in (await session.scalars(select(UserDirection.direction_id).where(UserDirection.user_id==user.id))).all())
        for a, o in await active_office_assignments(session, user.id):
            kind = a.scope_type or ('direction' if o.direction_id else 'department' if o.department_id else o.scope_type)
            ident = a.scope_id if a.scope_type else (o.direction_id or o.department_id or o.scope_id)
            if kind in {'department', 'direction'} and ident:
                result.add((kind, ident))
    return result


async def scope_options(session, user, settings, permission='tasks.manage'):
    allowed = await scopes(session, user, settings, permission)
    result = []
    if ('global', 0) in allowed:
        result.append({'kind': 'global', 'id': 0, 'name': 'Все лидеры'})
    for kind, model in (('department', Department), ('direction', Direction)):
        rows = (await session.scalars(select(model).order_by(model.name))).all()
        for row in rows:
            if ('global', 0) in allowed or (kind, row.id) in allowed:
                result.append({'kind': kind, 'id': row.id, 'name': row.name})
    return result


async def permitted_scope(session, user, settings, *, department_id=None, direction_id=None, permission='tasks.manage'):
    available = await scopes(session, user, settings, permission)
    if direction_id:
        direction = await session.get(Direction, direction_id)
        if not direction or department_id and direction.department_id != department_id:
            return False
    elif department_id and not await session.get(Department, department_id):
        return False
    if ('global', 0) in available:
        return True
    if direction_id:
        direction = await session.get(Direction, direction_id)
        if not direction or department_id and direction.department_id != department_id:
            return False
        return ('direction', direction_id) in available or ('department', direction.department_id) in available
    return bool(department_id and ('department', department_id) in available)


def in_scope(user, department_id=None, direction_id=None):
    if direction_id:
        return any(x.direction_id == direction_id for x in user.__dict__.get('directions',[]))
    if department_id:
        return any(x.department_id == department_id for x in user.__dict__.get('departments',[]))
    return True


async def user_in_scope(session, user, department_id=None, direction_id=None):
    if direction_id:
        return await session.scalar(select(UserDirection.id).where(UserDirection.user_id==user.id,UserDirection.direction_id==direction_id)) is not None
    if department_id:
        return await session.scalar(select(UserDepartment.id).where(UserDepartment.user_id==user.id,UserDepartment.department_id==department_id)) is not None
    return True


async def team(session, chat_id, *, query='', offset=0, limit=20, candidates=False):
    from app.database.leadership_models import LeaderChatMembership
    known = select(LeaderChatMembership.user_id).where(
        LeaderChatMembership.leader_chat_id == chat_id,
        LeaderChatMembership.membership_status.in_(['creator', 'administrator', 'member', 'restricted']),
        LeaderChatMembership.left_at.is_(None))
    stmt = select(User).where(User.is_archived.is_not(True), User.is_blocked.is_not(True))
    if not candidates:
        stmt = stmt.where(or_(User.id.in_(known), User.role.in_([Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN])))
    else:
        stmt = stmt.where(User.application_status == ApplicationStatus.APPROVED)
    value = query.strip().lstrip('@')[:100]
    if value:
        matches = [User.first_name.ilike(f'%{value}%'), User.last_name.ilike(f'%{value}%'), User.username.ilike(f'%{value}%')]
        if value.isdigit():
            matches.append(User.telegram_id == int(value))
        stmt = stmt.where(or_(*matches))
    stmt=stmt.order_by(User.first_name, User.id).offset(max(0,offset))
    if limit is not None: stmt=stmt.limit(min(100,max(1,limit)))
    return list((await session.scalars(stmt)).all())


async def set_leader(session, settings, actor, target_id, *, enabled, expected_role):
    from app.services.user_management_service import change_role
    if not await executive(session, actor, settings):
        raise PermissionError('Назначать лидеров могут председатель и заместитель.')
    target = await session.scalar(select(User).where(User.id == target_id).with_for_update()
                                  .execution_options(populate_existing=True))
    if not active(target) or target.application_status != ApplicationStatus.APPROVED:
        raise ValueError('Нужен действующий одобренный участник.')
    if target.role != expected_role:
        raise ValueError('Роль уже изменилась. Откройте участника заново.')
    if enabled and target.role not in {Role.PARTICIPANT, Role.ACTIVIST}:
        raise ValueError('Эта роль не заменяется статусом лидера.')
    if not enabled and target.role != Role.LEADER:
        raise ValueError('Снять можно только статус лидера, сохранив руководящие назначения.')
    result = await change_role(session, actor=actor, actor_telegram_id=actor.telegram_id, target=target,
                               new_role=Role.LEADER if enabled else Role.ACTIVIST, settings=settings)
    if not result.allowed:
        raise ValueError(result.reason)
    return target
