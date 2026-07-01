from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.database.models import AppSetting, ChatGreeting, Department, Direction, User
from app.utils.constants import Role

PRESERVED_TABLES = {
    "users",
    "departments",
    "directions",
    "badges",
    "app_settings",
    "offices",
    "chat_greetings",
}


async def reset_preview(
    session: AsyncSession, admin_telegram_ids: list[int]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        if table.name in PRESERVED_TABLES:
            continue
        value = int(await session.scalar(select(func.count()).select_from(table)) or 0)
        if value:
            counts[table.name] = value
    keep_admin = User.telegram_id.in_(admin_telegram_ids or [-1])
    non_admin_users = int(
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(~keep_admin, User.role != Role.ADMIN)
        )
        or 0
    )
    if non_admin_users:
        counts["users"] = non_admin_users
    return counts


async def reset_operational_data(
    session: AsyncSession, admin_telegram_ids: list[int]
) -> dict[str, int]:
    """Delete test activity while preserving admins and structural settings."""
    counts = await reset_preview(session, admin_telegram_ids)
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in PRESERVED_TABLES:
            continue
        await session.execute(delete(table))

    await session.execute(update(ChatGreeting).values(updated_by=None))
    await session.execute(update(AppSetting).values(updated_by=None))
    await session.execute(update(Department).values(leader_id=None))
    await session.execute(update(Direction).values(leader_id=None))
    await session.execute(update(User).values(archived_by=None))

    keep_admin = User.telegram_id.in_(admin_telegram_ids or [-1])
    await session.execute(delete(User).where(~keep_admin, User.role != Role.ADMIN))
    return counts
