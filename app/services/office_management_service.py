from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Office, User, UserOffice
from app.services.audit_service import audit

# "Должности и ответственность" — the Mini App equivalent of
# app/handlers/admin/offices_management.py (list/view/delete) and the
# office_assign/office_remove/office_new handlers in panel.py. Split across
# two bot files but one cohesive feature; kept together here as one
# service.


async def list_offices(session: AsyncSession, *, include_inactive: bool = False) -> list[Office]:
    conditions = [] if include_inactive else [Office.is_active.is_(True)]
    return list(
        (
            await session.scalars(
                select(Office).where(*conditions).order_by(Office.sort_order, Office.title)
            )
        ).all()
    )


async def create_office(session: AsyncSession, *, title: str, description: str | None) -> Office:
    office = Office(title=title, description=description)
    session.add(office)
    await session.flush()
    return office


async def list_assignments(session: AsyncSession, office_id: int) -> list[tuple[UserOffice, User]]:
    result = await session.execute(
        select(UserOffice, User)
        .join(User, User.id == UserOffice.user_id)
        .where(UserOffice.office_id == office_id, UserOffice.is_active.is_(True))
    )
    return list(result.all())


async def search_assignable_users(session: AsyncSession, query: str, *, limit: int = 8) -> list[User]:
    """Mirrors panel.py::office_assign_find's name/username/Telegram-ID
    search exactly, so the Mini App picker finds the same people the bot
    flow would."""
    stripped = query.strip().lstrip("@")
    conditions = [
        User.first_name.ilike(f"%{stripped}%"),
        User.last_name.ilike(f"%{stripped}%"),
        User.username.ilike(f"%{stripped}%"),
    ]
    if stripped.isdigit():
        conditions.append(User.telegram_id == int(stripped))
    return list((await session.scalars(select(User).where(or_(*conditions)).limit(limit))).all())


async def assign_office(
    session: AsyncSession, *, office_id: int, user_id: int, appointed_by_id: int
) -> UserOffice | None:
    """Returns None (no-op) if the user already holds an active assignment
    to this office — mirrors the bot's own de-duplication check."""
    existing = await session.scalar(
        select(UserOffice).where(
            UserOffice.office_id == office_id,
            UserOffice.user_id == user_id,
            UserOffice.is_active.is_(True),
        )
    )
    if existing is not None:
        return None
    assignment = UserOffice(office_id=office_id, user_id=user_id, appointed_by=appointed_by_id)
    session.add(assignment)
    await session.flush()
    return assignment


def remove_assignment(assignment: UserOffice) -> None:
    assignment.is_active = False
    assignment.ends_at = date.today()


async def delete_office(session: AsyncSession, office: Office, *, actor_id: int | None) -> int:
    """Soft-deletes the office and ends every active assignment — mirrors
    app/handlers/admin/offices_management.py::office_delete exactly,
    including the audit entry. Returns the number of assignments ended."""
    active_assignments = list(
        (
            await session.scalars(
                select(UserOffice).where(
                    UserOffice.office_id == office.id, UserOffice.is_active.is_(True)
                )
            )
        ).all()
    )
    for assignment in active_assignments:
        remove_assignment(assignment)
    office.is_active = False
    await audit(
        session,
        actor_id=actor_id,
        action="office.deleted",
        entity_type="office",
        entity_id=office.id,
        old_value={"title": office.title, "active_assignments": len(active_assignments)},
        new_value={"is_active": False},
    )
    return len(active_assignments)
