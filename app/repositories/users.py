from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
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


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


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

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=data["first_name"],
        last_name=data["last_name"],
        age=data["age"],
        phone=data["phone"],
        email=data.get("email"),
        city=data["city"],
        education_work=data["education_work"],
        occupation=data["occupation"],
        skills=data.get("skills", []),
        experience=data.get("experience"),
        motivation=data["motivation"],
        available_time=data["available_time"],
        desired_path=data["desired_path"],
        personal_data_consent=True,
        is_channel_subscribed=True,
        departments=[],
        directions=[],
    )
    session.add(user)
    await session.flush()
    await assign_interests(
        session,
        user,
        data.get("departments", []),
        data.get("directions", []),
    )
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
