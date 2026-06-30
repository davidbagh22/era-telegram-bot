from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, Badge, Department, Direction
from app.utils.constants import BADGES, DEPARTMENTS


DEPARTMENT_DESCRIPTIONS = {
    "Внутренние связи": (
        "Команды, мероприятия, культура, интерактив и развитие участников."
    ),
    "Внешние связи": (
        "Медиа, партнёрства, международные проекты, социальные инициативы "
        "и внешние коммуникации."
    ),
}


async def seed_reference_data(session: AsyncSession, settings: Settings) -> None:
    stored_settings = (await session.scalars(select(AppSetting))).all()
    for item in stored_settings:
        if hasattr(settings, item.key):
            setattr(settings, item.key, item.value)

    chat_urls = {
        "Внутренние связи": settings.internal_department_chat_url,
        "Внешние связи": settings.external_department_chat_url,
    }
    for department_name, direction_names in DEPARTMENTS.items():
        department = await session.scalar(
            select(Department).where(Department.name == department_name)
        )
        if department is None:
            department = Department(
                name=department_name,
                description=DEPARTMENT_DESCRIPTIONS[department_name],
                chat_url=chat_urls[department_name],
            )
            session.add(department)
            await session.flush()
        for direction_name in direction_names:
            exists = await session.scalar(
                select(Direction.id).where(
                    Direction.department_id == department.id,
                    Direction.name == direction_name,
                )
            )
            if not exists:
                session.add(Direction(department_id=department.id, name=direction_name))

    for badge_name in BADGES:
        exists = await session.scalar(select(Badge.id).where(Badge.name == badge_name))
        if not exists:
            session.add(Badge(name=badge_name))
    await session.commit()
