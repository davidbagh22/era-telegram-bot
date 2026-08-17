from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Office, User, UserOffice
from app.services.authorization_service import active_permissions, is_full_admin

# Leadership OS ToR section 14: "права принадлежат должности" -- an Office's
# permission_template is the single source of an appointment's permissions.
# Assigning a UserOffice turns the template on (scoped); the assignment
# ending (ends_at passing, is_active flipping) turns it back off. Manual
# PermissionGrant rows (app/services/authorization_service.py) stay a
# separate, deliberately-manual escape hatch (ToR section 16) -- this module
# unions both into one "effective permissions" view rather than replacing
# either.


@dataclass(frozen=True, slots=True)
class ScopedPermission:
    permission: str
    scope_type: str
    scope_id: int | None


def _office_scope(office: Office) -> tuple[str, int | None]:
    """An assignment's own scope override (set on UserOffice, e.g. a generic
    "Руководитель проекта" office appointed per-project) always wins; falling
    back to the office's own department/direction/scope_id (ToR section 15)."""
    if office.department_id is not None:
        return "department", office.department_id
    if office.direction_id is not None:
        return "direction", office.direction_id
    if office.scope_id is not None:
        return office.scope_type, office.scope_id
    return office.scope_type, None


def _assignment_scope(assignment: UserOffice, office: Office) -> tuple[str, int | None]:
    if assignment.scope_type is not None:
        return assignment.scope_type, assignment.scope_id
    return _office_scope(office)


def is_assignment_active(assignment: UserOffice, *, today: date | None = None) -> bool:
    """ToR section 25: acting/regular appointments both lose access the
    moment ends_at passes -- no separate "expire" step required."""
    if not assignment.is_active:
        return False
    today = today or date.today()
    if assignment.starts_at and assignment.starts_at > today:
        return False
    if assignment.ends_at and assignment.ends_at < today:
        return False
    return True


async def active_office_assignments(
    session: AsyncSession, user_id: int, *, today: date | None = None
) -> list[tuple[UserOffice, Office]]:
    rows = (
        await session.execute(
            select(UserOffice, Office)
            .join(Office, Office.id == UserOffice.office_id)
            .where(
                UserOffice.user_id == user_id,
                UserOffice.is_active.is_(True),
                Office.is_active.is_(True),
            )
        )
    ).all()
    today = today or date.today()
    return [(a, o) for a, o in rows if is_assignment_active(a, today=today)]


async def effective_scoped_permissions(
    session: AsyncSession, user: User, *, today: date | None = None
) -> set[ScopedPermission]:
    """Union of manual PermissionGrant rows and every active office
    assignment's permission_template, each carrying its own scope (ToR
    section 27: "Effective permissions = union всех активных assignments,
    каждый сохраняет собственный scope")."""
    result: set[ScopedPermission] = {
        ScopedPermission(grant.permission, grant.scope_type, grant.scope_id)
        for grant in (getattr(user, "permission_grants", None) or [])
        if grant.is_active
    }
    for assignment, office in await active_office_assignments(session, user.id, today=today):
        scope_type, scope_id = _assignment_scope(assignment, office)
        for permission in office.permission_template or []:
            result.add(ScopedPermission(permission, scope_type, scope_id))
    return result


def _matches(entry: ScopedPermission, permission: str, scope_type: str | None, scope_id: int | None) -> bool:
    if entry.permission != permission:
        return False
    if entry.scope_type == "global":
        return True
    if scope_type is None:
        # Caller didn't ask for a specific scope (legacy-style "does this
        # user have this permission anywhere?" check) -- any scoped grant
        # counts, mirroring authorization_service.active_permissions().
        return True
    return entry.scope_type == scope_type and entry.scope_id == scope_id


async def has_scoped_permission(
    session: AsyncSession,
    user: User | None,
    settings: Settings,
    telegram_id: int,
    permission: str,
    *,
    scope_type: str | None = None,
    scope_id: int | None = None,
) -> bool:
    """Server-side check combining permission + active appointment/grant +
    scope, per ToR section 95 -- frontend hiding is never authorization."""
    if is_full_admin(user, settings, telegram_id):
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    entries = await effective_scoped_permissions(session, user)
    return any(_matches(entry, permission, scope_type, scope_id) for entry in entries)


async def effective_permission_names(session: AsyncSession, user: User | None) -> set[str]:
    """Scope-blind view of effective_scoped_permissions -- a drop-in
    superset of authorization_service.active_permissions() that also counts
    office-template-derived permissions. Existing global boolean checks
    (can_manage_people, etc.) can adopt this without becoming scope-aware."""
    if user is None:
        return set()
    manual = active_permissions(user)
    scoped = await effective_scoped_permissions(session, user)
    return manual | {entry.permission for entry in scoped}


# --- Conflict detection (ToR section 28) -----------------------------------

_LEADERSHIP_ASSIGNMENT_WARNING_THRESHOLD = 3


async def detect_appointment_conflicts(session: AsyncSession, user_id: int) -> list[str]:
    """Advisory-only warnings for an admin about to appoint someone to a new
    office. Never blocks by itself (ToR section 28: "по умолчанию warning...
    не блокировать автоматически")."""
    assignments = await active_office_assignments(session, user_id)
    leadership_assignments = [
        (a, o) for a, o in assignments if o.permission_template
    ]
    warnings: list[str] = []
    if len(leadership_assignments) >= _LEADERSHIP_ASSIGNMENT_WARNING_THRESHOLD:
        warnings.append(
            f"У пользователя уже {len(leadership_assignments)} руководящих роли/ролей."
        )
    return warnings
