from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select

from app.config import Settings
from app.database.models import AppSetting, User
from app.services.notification_service import safe_send
from app.utils.constants import ApplicationStatus


BIRTHDAY_TEXT = """🎉 С днём рождения!

Команда ЭРА желает Вам сил, смелости, вдохновения и людей рядом, с которыми хочется создавать настоящее

Пусть этот год принесёт больше уверенности, классных проектов и возможностей, которые откроют новый этап Вашего пути 🌿"""


async def send_birthday_greetings(bot: Bot, settings: Settings, session_factory) -> int:
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    setting_key = f"birthday_greetings:{today:%Y-%m-%d}"
    sent_count = 0

    async with session_factory() as session:
        existing = await session.scalar(
            select(AppSetting).where(AppSetting.key == setting_key)
        )
        if existing:
            return 0

        users = (
            await session.scalars(
                select(User).where(
                    User.birth_date.is_not(None),
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_blocked.is_(False),
                    User.is_archived.is_(False),
                )
            )
        ).all()

        sent_user_ids: list[int] = []
        for user in users:
            if user.birth_date.month != today.month or user.birth_date.day != today.day:
                continue
            if await safe_send(bot, user.telegram_id, BIRTHDAY_TEXT):
                sent_count += 1
                sent_user_ids.append(user.id)

        session.add(
            AppSetting(
                key=setting_key,
                value={"sent_user_ids": sent_user_ids, "sent_count": sent_count},
            )
        )
        await session.commit()

    return sent_count
