from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Direction,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    Project,
    Task,
    User,
    UserDepartment,
    UserDirection,
)
from app.services.consent_service import CURRENT_POLICY_VERSION, record_consent
from app.services.referral_service import bind_referral_code
from app.utils.constants import ApplicationStatus, PointCategory
from app.utils.validators import calculate_age


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    """Resolve the canonical ERA user for a Telegram identity.

    The exact users.telegram_id match remains authoritative.  As a recovery
    path, use the Community Verification identity map when an older cleanup or
    import replaced the canonical user's Telegram id with a synthetic value.
    This prevents a real, previously registered Telegram account from being
    presented as "not registered" by both the bot and Mini App.

    We deliberately do not mutate/archive state here: identity resolution must
    be safe on a read path, while blocked/archived policy is still enforced by
    the caller.
    """
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is not None:
        return user

    # Local import avoids coupling the base User model to the optional
    # community-verification tables at module import time.
    from app.database.community_verification_models import CommunityMemberIdentity

    identity = await session.get(CommunityMemberIdentity, telegram_id)
    if identity is None or identity.user_id is None:
        return None

    linked_user = await session.get(User, identity.user_id)
    if linked_user is None:
        return None

    # A legacy dedup/archive flow used negative synthetic Telegram ids to keep
    # historical User rows without violating the unique constraint. If the
    # verified identity map still points at that same canonical row, restore
    # the real Telegram id and active state. This is narrowly scoped: normal
    # archived users keep their archive status, and an existing exact match
    # always won above.
    if linked_user.telegram_id < 0 and linked_user.telegram_id != telegram_id:
        linked_user.telegram_id = telegram_id
        linked_user.is_archived = False
        await session.flush()

    return linked_user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


def _birth_date_from_registration(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


async def create_user_from_registration(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    data: dict[str, Any],
) -> tuple[User, bool]:
    existing = await get_user_by_telegram_id(session, telegram_id)
    if existing is not None:
        return existing, False

    birth_date = _birth_date_from_registration(data.get("birth_date"))
    age = calculate_age(birth_date) if birth_date is not None else data.get("age")
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=data["first_name"],
        last_name=data.get("last_name"),
        birth_date=birth_date,
        age=age,
        phone=data.get("phone"),
        email=data.get("email"),
        country=data.get("country"),
        region=data.get("region"),
        city=data.get("city") or data.get("region"),
        education_work=data.get("education_work"),
        occupation=data.get("occupation") or data.get("education_work"),
        skills=data.get("skills", []),
        experience=data.get("experience"),
        motivation=data.get("motivation"),
        available_time=data.get("available_time"),
        desired_path=data.get("desired_path") or "Участник",
        application_status=ApplicationStatus.PENDING,
        personal_data_consent=True,
        is_channel_subscribed=True,
        departments=[],
        directions=[],
    )
    session.add(user)
    await session.flush()
    await record_consent(
        session,
        user_id=user.id,
        consent_type="registration",
        granted=True,
        source="bot",
        policy_version=str(data.get("consent_policy_version") or CURRENT_POLICY_VERSION),
    )
    await assign_interests(
        session,
        user,
        data.get("departments", []),
        data.get("directions", []),
    )
    try:
        await bind_referral_code(
            session,
            invitee=user,
            value=data.get("referral_code"),
        )
    except ValueError:
        pass
    return user, True


async def assign_interests(
    session: AsyncSession,
    user: User,
    department_names: Iterable[str],
    direction_names: Iterable[str],
) -> None:
    department_names = set(department_names)
    direction_names = set(direction_names)
    departments = (
        await session.scalars(
            select(Department).where(Department.name.in_(department_names))
        )
    ).all()
    directions = (
        await session.scalars(
            select(Direction).where(Direction.name.in_(direction_names))
        )
    ).all()
    user.departments = [
        UserDepartment(department=department, status="interested")
        for department in departments
    ]
    user.directions = [
        UserDirection(direction=direction, status="interested")
        for direction in directions
    ]


async def user_stats(session: AsyncSession, user_id: int) -> dict[str, int]:
    async def count(model: type, condition: Any) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(model).where(condition)
            )
            or 0
        )

    points = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == user_id
            )
        )
        or 0
    )
    return {
        "points": points,
        "events": await count(EventRegistration, EventRegistration.user_id == user_id),
        "projects": await count(Project, Project.author_id == user_id),
        "completed_projects": await count(
            Project, (Project.author_id == user_id) & (Project.status == "completed")
        ),
        "tasks": await count(
            Task, (Task.assignee_id == user_id) & (Task.status == "completed")
        ),
        "portfolio": await count(PortfolioItem, PortfolioItem.user_id == user_id),
    }


async def rating(session: AsyncSession, limit: int = 10) -> list[tuple[User, int]]:
    rows = (
        await session.execute(
            select(
                User, func.coalesce(func.sum(PointTransaction.points), 0).label("score")
            )
            .outerjoin(PointTransaction, PointTransaction.user_id == User.id)
            .where(User.application_status == "approved", User.is_blocked.is_(False))
            .group_by(User.id)
            .order_by(func.sum(PointTransaction.points).desc().nullslast(), User.id)
            .limit(limit)
        )
    ).all()
    return [(user, int(score)) for user, score in rows]


async def weekly_rating(
    session: AsyncSession, *, week_start: datetime, limit: int = 10
) -> list[tuple[User, int]]:
    rows = (
        await session.execute(
            select(
                User, func.coalesce(func.sum(PointTransaction.points), 0).label("score")
            )
            .outerjoin(
                PointTransaction,
                (PointTransaction.user_id == User.id)
                & (PointTransaction.created_at >= week_start)
                & (PointTransaction.points > 0)
                & or_(
                    PointTransaction.category.is_(None),
                    PointTransaction.category != PointCategory.DIGITAL_ENGAGEMENT,
                ),
            )
            .where(User.application_status == "approved", User.is_blocked.is_(False))
            .group_by(User.id)
            .having(func.coalesce(func.sum(PointTransaction.points), 0) > 0)
            .order_by(func.sum(PointTransaction.points).desc().nullslast(), User.id)
            .limit(limit)
        )
    ).all()
    return [(user, int(score)) for user, score in rows]
