from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import desc, select

from app.config import Settings
from app.database.development_models import AssessmentConsent, DevelopmentAuditLog, MonthlyCheckin
from app.database.models import User
from app.utils.constants import ApplicationStatus
from app.utils.deep_links import miniapp_path_url

REMINDER_ACTION = "development.monthly_checkin_reminder.sent"


async def send_monthly_development_reminders(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Send at most one guilt-free My Vector reminder per user per month.

    The scheduler calls this daily so a service restart cannot make the whole
    month miss its reminder. Delivery is idempotent through the development
    audit table. Only the latest consent record is honored; a later withdrawal
    stops future reminders even if an older accepted consent exists.
    """
    miniapp_url = settings.effective_miniapp_url
    if not miniapp_url:
        return

    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    checkin_url = miniapp_path_url(miniapp_url, "development/checkin/current")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверить себя", web_app=WebAppInfo(url=checkin_url))]
        ]
    )

    async with session_factory() as session:
        users = list(
            (
                await session.scalars(
                    select(User).where(
                        User.application_status == ApplicationStatus.APPROVED,
                        User.is_archived.is_(False),
                        User.is_blocked.is_(False),
                    )
                )
            ).all()
        )

        for user in users:
            consent = await session.scalar(
                select(AssessmentConsent)
                .where(AssessmentConsent.user_id == user.id)
                .order_by(desc(AssessmentConsent.created_at), desc(AssessmentConsent.id))
                .limit(1)
            )
            if consent is None or not consent.accepted:
                continue

            completed = await session.scalar(
                select(MonthlyCheckin.id).where(
                    MonthlyCheckin.user_id == user.id,
                    MonthlyCheckin.month == month,
                    MonthlyCheckin.status == "completed",
                )
            )
            if completed is not None:
                continue

            already_sent = await session.scalar(
                select(DevelopmentAuditLog.id).where(
                    DevelopmentAuditLog.target_user_id == user.id,
                    DevelopmentAuditLog.action == REMINDER_ACTION,
                    DevelopmentAuditLog.created_at >= month_start,
                )
            )
            if already_sent is not None:
                continue

            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "Твой новый Check-in готов\n\n"
                        "Прошёл ещё один месяц. За 5 минут можно увидеть, что у тебя изменилось.\n\n"
                        "Без оценок и обязательных серий — только твоя собственная динамика."
                    ),
                    reply_markup=keyboard,
                )
            except Exception:
                # One unreachable Telegram account must not block the reminder
                # run for the rest of the community. We intentionally do not
                # log message payloads or personal profile data here.
                continue

            session.add(
                DevelopmentAuditLog(
                    actor_user_id=None,
                    target_user_id=user.id,
                    action=REMINDER_ACTION,
                    metadata_json={"month": month},
                )
            )

        await session.commit()
