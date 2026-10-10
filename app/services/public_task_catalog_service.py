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
import asyncio
import logging
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, Task, User
from app.services.notification_service import safe_send_once
from app.services.general_topics_service import send_general_topic
from app.utils.constants import ApplicationStatus, Role


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
    if session.bind.dialect.name == 'postgresql':
        await session.execute(sql_text('SELECT pg_advisory_xact_lock(2026101020)'))
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
            task = Task(title=str(item["title"]), description=str(item["description"]) + "\n\nВыполните задание, затем нажмите «Отправить результат» в боте. Если материал уже отправлен в @era_leaders, приложите ссылку или скриншот отправки. Нажмите «Подтвердить отправку». Баллы начисляются один раз после проверки администратором.", assignee_id=None, creator_id=creator.id, deadline=deadline, points=int(item["points"]), task_type="challenge", status="published", max_participants=None, reward_json=reward)
            session.add(task)
            await session.flush()
            created += 1
        tasks.append(task)

    # Persist tasks before transport, snapshot the audience once, then retry
    # individual durable deliveries without creating another campaign.
    row = await session.scalar(select(AppSetting).where(AppSetting.key == 'public_catalog_launch_v2'))
    if row is None:
        ids = list((await session.scalars(select(User.id).where(
            User.application_status == ApplicationStatus.APPROVED,
            User.is_blocked.is_(False), User.is_archived.is_(False)))).all())
        row = AppSetting(key='public_catalog_launch_v2', value={'recipient_ids': ids}, updated_by=creator.id)
        session.add(row)
    recipient_ids = row.value['recipient_ids']
    await session.commit()
    sent = failed = 0
    if bot is not None:
        username = settings.bot_username.strip('@') or (await bot.get_me()).username
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🎯 20 заданий и баллы', url=f'https://t.me/{username}?start=tasks_catalog')],
            [InlineKeyboardButton(text='📚 Читать и подписаться', url=f'https://t.me/{username}?start=bookclub')],
        ])
        message = (
            '✨ Две новые возможности в ЭРА\n\n'
            '🎯 Выберите своё задание\nСнять ролик, придумать событие, создать дизайн или найти партнёра. '
            'В каталоге 20 заданий: за каждое — 80, 150 или 200 баллов после проверки. '
            'Выполнять всё не нужно. Подтверждённые работы попадают в портфолио.\n\n'
            '💡 Есть своя идея? Предложите проект: проблема, для кого он, план на 30 дней, команда и ресурсы. '
            'Лучший проект получит поддержку и реализацию, сертификат, баллы и запись в портфолио. '
            'Победителя выбирает команда ЭРА по пользе, реализуемости и готовности автора участвовать.\n\n'
            '📚 Читаем вместе\nНачинаем с «48 законов власти» Роберта Грина: '
            '48 авторских критических разборов, примеры и вопросы для себя. '
            'Это не полный текст книги. По добровольной подписке — выпуск в 19:00 по Еревану. '
            'Если формат понравится, продолжим с другими книгами.\n\n'
            'Выбирайте кнопку. Новым участникам сначала нужно пройти регистрацию в боте.'
        )
        for user_id in recipient_ids:
            user = await session.get(User, user_id)
            if not user or user.is_blocked or user.is_archived or user.application_status != ApplicationStatus.APPROVED:
                continue
            result = await safe_send_once(bot, settings, user.telegram_id, message,
                delivery_key=f'public-catalog-v2:{user.id}', notification_type='public_catalog', reply_markup=keyboard)
            sent += int(result.sent)
            failed += int(not result.sent)
            await asyncio.sleep(0.05)
        group_sent = await send_general_topic(bot, settings, 'notifications', message,
            reply_markup=keyboard, delivery_key='public-catalog-v2')
    else:
        group_sent = False
    return {'created': created, 'total': len(tasks), 'sent': sent, 'failed': failed, 'group_sent': group_sent}


async def show_catalog(message, session, user):
    tasks = (await session.scalars(select(Task).where(Task.task_type == 'challenge', Task.status == 'published').order_by(Task.id))).all()
    tasks = [t for t in tasks if (t.reward_json or {}).get('public_task')]
    if not tasks:
        await message.answer('Каталог готовится. Попробуйте открыть его позже.')
        return
    rows = [[InlineKeyboardButton(text=f'{i}. {t.title} · {t.points} б.', callback_data=f'task:view:{t.id}')] for i, t in enumerate(tasks, 1)]
    rows.append([InlineKeyboardButton(text='🏠 Главное меню', callback_data='menu:main')])
    await message.answer('🎯 Выберите одно или несколько заданий. Баллы начисляются после подтверждения результата администратором.', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def launch_catalog_job(bot, settings, session_factory):
    async with session_factory() as session:
        creator = await session.scalar(select(User).where(User.role == Role.ADMIN, User.is_blocked.is_(False), User.is_archived.is_(False)).order_by(User.id))
        if creator is None:
            return
        result = await publish_catalog(session, creator=creator, bot=bot, settings=settings)
        logging.getLogger(__name__).info('Public catalog launch result: %s', result)
