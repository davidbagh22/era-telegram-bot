"""Guest RSVP for the owner's 12 December 2026 anniversary; no membership writes."""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppSetting

PAYLOAD = "anniversary2026"
PREFIX = "anniversary:2026:guest:"
START = datetime(2026, 12, 12, 17, 30, tzinfo=ZoneInfo("Asia/Yerevan"))
DETAILS = "Годовщина ЭРЫ\n12 декабря 2026, 17:30\nКинозал Дома Москвы в Ереване"


def registration_open(now: datetime | None = None) -> bool:
    return (now or datetime.now(START.tzinfo)) < START


def clean_field(value: str, *, name: bool = False) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError("Введите ответ одной строкой.")
    value = " ".join(value.split())
    if not value or len(value) > (80 if name else 160) or value.startswith("/"):
        raise ValueError("Введите короткий ответ: до 80 символов для имени и фамилии, до 160 для организации.")
    if name and not any(c.isalpha() for c in value):
        raise ValueError("Укажите имя или фамилию буквами.")
    return value


async def get_registration(session: AsyncSession, telegram_id: int) -> dict | None:
    return await session.scalar(select(AppSetting.value).where(AppSetting.key == f"{PREFIX}{telegram_id}"))


async def register(session: AsyncSession, telegram_id: int, data: dict) -> dict:
    if not registration_open():
        raise ValueError("Регистрация на годовщину завершена.")
    value = {
        "first_name": clean_field(data.get("first_name"), name=True),
        "last_name": clean_field(data.get("last_name"), name=True),
        "organization": clean_field(data.get("organization")),
        "telegram_id": telegram_id,
        "registered_at": datetime.now(START.tzinfo).isoformat(),
        "consent_version": "anniversary2026-v1",
    }
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise RuntimeError("Unsupported RSVP database")
    await session.execute(insert(AppSetting).values(key=f"{PREFIX}{telegram_id}", value=value)
                          .on_conflict_do_nothing(index_elements=["key"]))
    # Persist before sending success: a failed Telegram reply cannot lose the RSVP.
    await session.commit()
    return await get_registration(session, telegram_id)
