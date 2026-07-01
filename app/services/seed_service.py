from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    AppSetting,
    Badge,
    ChatGreeting,
    Department,
    Direction,
    Office,
)
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

OFFICE_TITLES = (
    ("Председатель", 10),
    ("Заместитель председателя", 20),
    ("Член Совета", 30),
    ("Руководитель внутренних связей", 40),
    ("Заместитель руководителя внутренних связей", 50),
    ("Руководитель внешних связей", 40),
    ("Заместитель руководителя внешних связей", 50),
    ("Лидер направления «Лидерство»", 60),
    ("Лидер направления «Культура»", 60),
    ("Лидер направления «Интерактив»", 60),
    ("Лидер международного направления", 60),
    ("Лидер направления «Медиа»", 60),
    ("Лидер направления «Социальные инициативы»", 60),
)

GREETING_DEFAULTS = {
    "general": (
        "Добро пожаловать в ЭРА",
        "Рады видеть Вас в общем чате ЭРА 🤝\n\n"
        "Здесь знакомятся, находят единомышленников и превращают идеи в действия\n\n"
        "Начните с короткого знакомства: как Вас зовут и что Вам интересно",
    ),
    "internal": (
        "Внутренние связи",
        "Добро пожаловать в команду внутренних связей 🌿\n\n"
        "Здесь развивают культуру сообщества, лидерство и командные форматы",
    ),
    "external": (
        "Внешние связи",
        "Добро пожаловать в команду внешних связей 🌍\n\n"
        "Здесь рождаются медиа, партнёрства, международные и социальные инициативы",
    ),
    "leaders": (
        "Команда лидеров",
        "Добро пожаловать в рабочее пространство лидеров ЭРА\n\n"
        "Здесь принимают решения, поддерживают команды и доводят идеи до результата",
    ),
}


async def seed_reference_data(session: AsyncSession, settings: Settings) -> None:
    stored_settings = (await session.scalars(select(AppSetting))).all()
    for item in stored_settings:
        if hasattr(settings, item.key):
            value = (
                int(item.value)
                if item.key.endswith("_id") and str(item.value).lstrip("-").isdigit()
                else item.value
            )
            setattr(settings, item.key, value)

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

    for title, sort_order in OFFICE_TITLES:
        exists = await session.scalar(select(Office.id).where(Office.title == title))
        if not exists:
            session.add(Office(title=title, sort_order=sort_order))

    chat_ids = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }
    for chat_key, (title, text) in GREETING_DEFAULTS.items():
        exists = await session.scalar(
            select(ChatGreeting.id).where(ChatGreeting.chat_key == chat_key)
        )
        if not exists:
            session.add(
                ChatGreeting(
                    chat_key=chat_key,
                    chat_id=chat_ids[chat_key],
                    title=title,
                    text=text,
                )
            )
    await session.commit()
