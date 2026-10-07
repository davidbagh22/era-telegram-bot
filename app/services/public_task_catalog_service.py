"""The small, repeatable public-task launch campaign.

The catalog is deliberately data-driven and idempotent: running the admin action
twice never creates a second copy of the same mission.  Telegram delivery is
best-effort; the task catalog remains available in the bot even when a chat is
not bound or a participant has blocked the bot.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, User
from app.services.notification_service import safe_send
from app.utils.constants import ApplicationStatus


CATALOG: tuple[dict[str, object], ...] = (
    {"key": "intro_video", "title": "Сними короткое видео об ЭРА", "description": "30–60 секунд: кто ты, чем полезна ЭРА и почему стоит присоединиться. Отправь видео в @era_leaders.", "points": 80, "counts": ["media"]},
    {"key": "era_story", "title": "Опубликуй историю об ЭРА", "description": "Сделай сторис или пост о своём опыте в ЭРА и пришли ссылку или скриншот.", "points": 80, "counts": ["media", "social"]},
    {"key": "invite_three", "title": "Пригласи 3 подходящих участника", "description": "Расскажи о боте трём людям, которым могут быть полезны проекты и сообщество. Передай им ссылку на бота.", "points": 80, "counts": ["social"]},
    {"key": "partner_contact", "title": "Найди одного партнёра", "description": "Предложи организацию, университет или бизнес для сотрудничества и укажи контакт/ссылку.", "points": 150, "counts": ["partner"]},
    {"key": "opportunity", "title": "Найди возможность для команды", "description": "Подбери конкурс, грант, стажировку или мероприятие и пришли ссылку с коротким объяснением.", "points": 80, "counts": ["project"]},
    {"key": "channel_post", "title": "Придумай пост для канала", "description": "Напиши готовую идею поста: заголовок, текст и призыв к действию для аудитории ЭРА.", "points": 80, "counts": ["media"]},
    {"key": "poster", "title": "Сделай афишу или обложку", "description": "Создай визуал для события или набора в команду. Прикрепи изображение или ссылку на макет.", "points": 150, "counts": ["media"]},
    {"key": "translation", "title": "Переведи материал ЭРА", "description": "Переведи короткий текст о проекте на английский или армянский и пришли текст файлом или сообщением.", "points": 80, "counts": ["media"]},
    {"key": "why_era", "title": "Запиши видео «Почему я с ЭРА»", "description": "30 секунд о том, что даёт тебе сообщество и что ты хочешь изменить.", "points": 80, "counts": ["media"]},
    {"key": "event_idea", "title": "Предложи идею мероприятия", "description": "Опиши формат, тему, аудиторию, место и ожидаемый результат будущего события.", "points": 150, "counts": ["project"]},
    {"key": "universities", "title": "Составь список 5 сообществ", "description": "Найди 5 университетов, молодёжных объединений или клубов, которым можно предложить партнёрство.", "points": 150, "counts": ["partner"]},
    {"key": "venue", "title": "Найди площадку для события", "description": "Предложи площадку или онлайн-сервис: ссылка, контакты, вместимость и условия.", "points": 80, "counts": ["partner"]},
    {"key": "faq", "title": "Подготовь 5 ответов новичку", "description": "Напиши понятные ответы на вопросы: что такое ЭРА, как вступить, где задания, как получить баллы и что даёт портфолио.", "points": 80, "counts": ["social"]},
    {"key": "reel", "title": "Сделай Reels/Shorts о сообществе", "description": "Смонтируй короткий вертикальный ролик о людях, проектах или возможностях ЭРА.", "points": 150, "counts": ["media"]},
    {"key": "photo_selection", "title": "Собери фотоисторию события", "description": "Подбери 5–10 фотографий с подписями и предложи порядок публикации.", "points": 80, "counts": ["media"]},
    {"key": "help_initiative", "title": "Предложи инициативу помощи", "description": "Сформулируй небольшую инициативу для сообщества: проблема, кому помогаем, первый шаг и нужные ресурсы.", "points": 150, "counts": ["volunteering", "project"]},
    {"key": "media_contact", "title": "Найди медиа-возможность", "description": "Подбери СМИ, блогера или подкаст для рассказа об ЭРА и пришли контакт/ссылку.", "points": 80, "counts": ["partner", "media"]},
    {"key": "partner_letter", "title": "Напиши письмо партнёру", "description": "Составь короткое готовое письмо с предложением сотрудничества от имени ЭРА.", "points": 150, "counts": ["partner"]},
    {"key": "quiz", "title": "Составь мини-викторину", "description": "Придумай 5 вопросов об ЭРА, культуре, лидерстве или проектной работе с вариантами ответов.", "points": 80, "counts": ["culture"]},
    {"key": "project_competition", "title": "Предложи свой проект", "description": "Опиши проблему, цель, аудиторию, план на 30 дней, команду и нужные ресурсы. Лучший проект получит поддержку и реализацию, сертификат, баллы и запись в портфолио.", "points": 200, "counts": ["project"], "project_competition": True},
)


async def publish_catalog(session: AsyncSession, *, creator: User, bot: Bot | None, settings: Settings) -> dict[str, int]:
    deadline = datetime.now(timezone.utc) + timedelta(days=30)
    created = 0
    tasks: list[Task] = []
    existing = list((await session.scalars(select(Task).where(Task.task_type == "challenge"))).all())
    existing_by_key = {str((task.reward_json or {}).get("catalog_key")): task for task in existing}
    for item in CATALOG:
        key = str(item["key"])
        task = existing_by_key.get(key)
        if task is None:
            reward = {"catalog_key": key, "public_task": True, "counts_toward": list(item["counts"])}
            if item.get("project_competition"):
                reward.update({"project_competition": True, "portfolio_on_approval": True})
            task = Task(title=str(item["title"]), description=str(item["description"]), assignee_id=None, creator_id=creator.id, deadline=deadline, points=int(item["points"]), task_type="challenge", status="published", max_participants=50, reward_json=reward)
            session.add(task)
            await session.flush()
            created += 1
        tasks.append(task)

    sent = 0
    if bot is not None:
        catalog_url = f"https://t.me/{settings.bot_username}?start=tasks_catalog" if settings.bot_username else settings.effective_miniapp_url
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Задания и баллы", url=catalog_url)],
            [InlineKeyboardButton(text="📖 Книжный клуб", url=catalog_url)],
        ]) if catalog_url else None
        message = ("🎯 Новые задания ЭРА\n\n"
                   "1) 🎯 Задания и баллы — выберите любую миссию из 20; лучшие работы попадают в портфолио.\n"
                   "2) 📖 Книжный клуб — 48 дней авторских разборов и вопросов по книге.\n\n"
                   "Для задания отправьте результат и подтвердите отправку. Админ проверит работу и начислит баллы.")
        recipients = await session.scalars(select(User.telegram_id).where(User.application_status == ApplicationStatus.APPROVED, User.is_blocked.is_(False), User.is_archived.is_(False)))
        for telegram_id in recipients.all():
            if await safe_send(bot, int(telegram_id), message, reply_markup=keyboard):
                sent += 1
        if settings.general_chat_id:
            await safe_send(bot, settings.general_chat_id, message, reply_markup=keyboard)
    return {"created": created, "total": len(tasks), "sent": sent}
