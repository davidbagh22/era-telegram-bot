"""Opt-in daily reading club; summaries are original and do not reproduce the book."""
from __future__ import annotations

from datetime import date, datetime, timezone
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, User
from app.services.notification_service import safe_send_once

LAW_TITLES = (
    "Никогда не затмевай господина", "Не доверяй слишком друзьям; учись использовать врагов",
    "Скрывай свои намерения", "Всегда говори меньше, чем кажется необходимым",
    "Так много зависит от репутации — береги её ценой жизни", "Добивайся внимания любой ценой",
    "Заставь других работать на себя, а себе оставь заслуги", "Заставь людей приходить к тебе — при необходимости используй приманку",
    "Побеждай действиями, а не спорами", "Заражение: избегай несчастливых и невезучих",
    "Учись держать людей в зависимости от себя", "Используй избирательную честность и щедрость, чтобы обезоружить жертву",
    "Прося о помощи, взывай к корысти людей", "Выступай как друг, работай как шпион",
    "Разгроми врага полностью", "Используй отсутствие, чтобы усилить уважение и почёт",
    "Держи других в подвешенном состоянии: культивируй атмосферу непредсказуемости",
    "Не строй крепость, чтобы защитить себя — изоляция опасна", "Знай, с кем имеешь дело — не оскорбляй не того человека",
    "Не связывайся ни с кем", "Выгляди глупее своего объекта, чтобы он чувствовал себя умным",
    "Используй капитуляцию как инструмент власти", "Сосредоточь силы", "Будь королевским в манере — веди себя как король, чтобы с тобой обращались соответственно",
    "Воссоздай себя", "Держи руки чистыми", "Играя на вере людей в необходимость, создавай культ последователей",
    "Вступай в действие смело", "Планируй всё до конца", "Сделай свои достижения лёгкими",
    "Управляй вариантами: пусть другие играют картами, которые ты раздаёшь", "Играй на фантазиях людей",
    "Открой слабости каждого", "Будь по-королевски пренебрежителен к тому, чего не можешь иметь",
    "Создавай убедительные зрелища", "Думай как хочешь, но веди себя как другие",
    "Взбаламучивай воду, чтобы поймать рыбу", "Презирай бесплатный обед",
    "Избегай следов: не ступай в чужую обувь", "Бей пастуха — и овцы разбегутся",
    "Работай на сердца и умы других", "Обезоружь и разозли зеркальным эффектом",
    "Проповедуй необходимость перемен, но никогда не меняй слишком много сразу",
    "Никогда не выгляди слишком совершенным", "Не переходи намеченную цель — в победе умей остановиться",
    "Будь изменчив, как вода", "Научись находить точку опоры для влияния", "Будь бесформенным",
)

def _summary(title: str) -> str:
    return f"Идея дня: {title}. Рассмотрите этот принцип критически: где он может помочь понять динамику людей, а где его применение разрушает доверие. Это авторский пересказ для обсуждения, не текст книги."

async def start(session: AsyncSession, *, actor: User) -> date:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == "book_club_start_date"))
    today = datetime.now(timezone.utc).date()
    if row is None:
        row = AppSetting(key="book_club_start_date", value={"date": today.isoformat()}, updated_by=actor.id)
        session.add(row)
    return date.fromisoformat(row.value_json["date"])

async def daily_job(bot: Bot, settings: Settings, session_factory) -> None:
    async with session_factory() as session:
        row = await session.scalar(select(AppSetting).where(AppSetting.key == "book_club_start_date"))
        if row is None:
            return
        start_day = date.fromisoformat(row.value["date"])
        day = (datetime.now(timezone.utc).date() - start_day).days
        if day < 0 or day >= len(LAW_TITLES):
            return
        title = LAW_TITLES[day]
        text = (f"📖 Книжный клуб ЭРА — день {day + 1}/48\n\n<b>{title}</b>\n\n"
                f"{_summary(title)}\n\nВопросы для себя:\n1) Где я уже сталкивался с такой динамикой?\n2) Как применить идею этично — без манипуляции?\n3) Какой вывод возьму в работу сегодня?")
        users = await session.scalars(select(User).where(User.book_club_subscribed.is_(True), User.is_blocked.is_(False), User.is_archived.is_(False)))
        for user in users.all():
            await safe_send_once(bot, settings, user.telegram_id, text, delivery_key=f"book-club:{start_day.isoformat()}:{day}:{user.id}", notification_type="book_club")
        # Public literature posts require a dedicated forum topic and reviewed content.
        # Never leak daily messages into the general chat main thread.
        await session.commit()
