from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.content.community_missions_pack import load_community_missions
from app.database.community_models import CommunityMissionTemplate, TaskSquad, TaskSubtask
from app.database.models import Task, TaskParticipant, TaskSubmission, User

logger = logging.getLogger(__name__)

CATEGORY_ROLES: dict[str, list[tuple[str, str]]] = {
    "research": [
        ("coordinator", "Координатор"),
        ("research", "Исследование"),
        ("analysis", "Аналитика"),
        ("report", "Отчёт"),
    ],
    "community": [
        ("coordinator", "Координатор"),
        ("research", "Исследование"),
        ("onboarding", "Работа с участниками"),
        ("analytics", "Аналитика"),
        ("report", "Отчёт"),
    ],
    "interactive": [
        ("coordinator", "Координатор"),
        ("scenario", "Сценарий"),
        ("host", "Ведущий"),
        ("logistics", "Логистика"),
        ("analytics", "Аналитика"),
    ],
    "culture": [
        ("coordinator", "Координатор"),
        ("research", "Исследование"),
        ("scenario", "Сценарий / программа"),
        ("host", "Ведущий"),
        ("media", "Медиа"),
    ],
    "media": [
        ("coordinator", "Координатор"),
        ("text", "Текст"),
        ("design", "Дизайн"),
        ("photo", "Фото"),
        ("video", "Видео"),
        ("editing", "Монтаж"),
        ("stories", "Stories"),
        ("analytics", "Аналитика"),
    ],
    "social": [
        ("coordinator", "Координатор"),
        ("partners", "Партнёры"),
        ("logistics", "Логистика"),
        ("registration", "Регистрация / участники"),
        ("report", "Отчёт"),
    ],
    "partner": [
        ("coordinator", "Координатор"),
        ("research", "Исследование"),
        ("partners", "Партнёры"),
        ("text", "Коммуникация / текст"),
        ("report", "Отчёт"),
    ],
    "leadership": [
        ("coordinator", "Координатор"),
        ("mentor", "Наставничество"),
        ("facilitator", "Фасилитация"),
        ("analytics", "Аналитика"),
        ("report", "Отчёт"),
    ],
    "mentorship": [
        ("coordinator", "Координатор"),
        ("mentor", "Наставник"),
        ("onboarding", "Первый шаг новичка"),
        ("analytics", "Фиксация результата"),
        ("report", "Передача опыта"),
    ],
    "project": [
        ("coordinator", "Координатор"),
        ("concept", "Концепция"),
        ("partners", "Партнёры"),
        ("logistics", "Логистика"),
        ("registration", "Регистрация"),
        ("media", "Медиа"),
        ("analytics", "Аналитика"),
        ("report", "Отчёт"),
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _mission_meta(task: Task) -> dict:
    return (task.reward_json or {}).get("community_mission") or {}


def is_community_mission_task(task: Task) -> bool:
    return bool(_mission_meta(task).get("code"))


def workspace_chat_id(settings: Settings, chat_key: str) -> int | None:
    return {
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "media": settings.media_chat_id,
        "general": settings.general_chat_id,
        "leaders": settings.leaders_chat_id,
    }.get(chat_key)


async def seed_community_missions(session: AsyncSession) -> None:
    for item in load_community_missions():
        exists = await session.scalar(
            select(CommunityMissionTemplate.id).where(
                CommunityMissionTemplate.code == item["code"]
            )
        )
        if exists:
            continue
        session.add(
            CommunityMissionTemplate(
                code=item["code"],
                month=int(item["month"]),
                title=item["title"],
                description=item["description"],
                category=item["category"],
                claim_mode=item["claim_mode"],
                min_people=int(item["min_people"]),
                max_people=int(item["max_people"]),
                workspace_chat_key=item["workspace_chat_key"],
                deadline_days=int(item["deadline_days"]),
                deliverable=item["deliverable"],
                points=int(item["points"]),
                counts_toward=list(item.get("counts_toward") or []),
                repeatable=bool(item.get("repeatable", True)),
                is_active=True,
            )
        )
    await session.flush()


async def list_mission_templates(
    session: AsyncSession, *, month: int | None = None
) -> list[CommunityMissionTemplate]:
    stmt = select(CommunityMissionTemplate).where(
        CommunityMissionTemplate.is_active.is_(True)
    )
    if month is not None:
        stmt = stmt.where(CommunityMissionTemplate.month == month)
    rows = await session.scalars(
        stmt.order_by(CommunityMissionTemplate.month, CommunityMissionTemplate.code)
    )
    return list(rows.all())


async def launch_mission(
    session: AsyncSession,
    template: CommunityMissionTemplate,
    *,
    creator_id: int,
    starts_at: datetime | None = None,
) -> Task:
    start = _aware(starts_at) if starts_at else _now()
    deadline = start + timedelta(days=max(1, int(template.deadline_days)))
    task = Task(
        title=template.title,
        description=template.description,
        creator_id=creator_id,
        deadline=deadline,
        points=template.points,
        status="published",
        task_type="challenge",
        audience_filter_json={},
        reward_json={
            "counts_toward": list(template.counts_toward or []),
            "community_mission": {
                "template_id": template.id,
                "code": template.code,
                "month": template.month,
                "category": template.category,
                "claim_mode": template.claim_mode,
                "min_people": template.min_people,
                "max_people": template.max_people,
                "workspace_chat_key": template.workspace_chat_key,
                "deliverable": template.deliverable,
            },
        },
        max_participants=template.max_people,
        remind_at=deadline - timedelta(hours=24),
    )
    session.add(task)
    await session.flush()
    return task


async def _joined_user_ids(session: AsyncSession, task_id: int) -> list[int]:
    rows = await session.scalars(
        select(TaskParticipant.user_id)
        .where(
            TaskParticipant.task_id == task_id,
            TaskParticipant.status.in_(["accepted", "joined"]),
        )
        .order_by(TaskParticipant.id)
    )
    return list(rows.all())


async def _ensure_subtask_proposal(
    session: AsyncSession, task: Task, squad: TaskSquad, user_ids: list[int]
) -> None:
    existing = int(
        await session.scalar(
            select(func.count(TaskSubtask.id)).where(TaskSubtask.squad_id == squad.id)
        )
        or 0
    )
    if existing:
        return
    meta = _mission_meta(task)
    category = str(meta.get("category") or "project")
    roles = CATEGORY_ROLES.get(category, CATEGORY_ROLES["project"])
    minimum = max(1, int(meta.get("min_people") or 1))
    count = min(len(roles), max(minimum, len(user_ids)))
    for index, (role_key, title) in enumerate(roles[:count]):
        session.add(
            TaskSubtask(
                squad_id=squad.id,
                role_key=role_key,
                title=title,
                description=f"Ответственность «{title}» внутри задачи «{task.title}».",
                assignee_id=user_ids[index % len(user_ids)] if user_ids else None,
                deadline=task.deadline,
                status="proposed",
                deliverable=str(meta.get("deliverable") or task.description)[:1000],
                metadata_json={"auto_proposed": True},
            )
        )
    await session.flush()


async def sync_task_squad_after_claim(
    session: AsyncSession, task: Task, *, participant_user_id: int
) -> TaskSquad | None:
    if not is_community_mission_task(task):
        return None
    meta = _mission_meta(task)
    squad = await session.scalar(select(TaskSquad).where(TaskSquad.task_id == task.id))
    if squad is None:
        deadline = _aware(task.deadline)
        total_seconds = max(0.0, (deadline - _now()).total_seconds())
        squad = TaskSquad(
            task_id=task.id,
            responsible_user_id=participant_user_id,
            workspace_chat_key=str(meta.get("workspace_chat_key") or "internal"),
            status="forming",
            checkpoint_at=_now() + timedelta(seconds=total_seconds / 2),
        )
        session.add(squad)
        await session.flush()

    user_ids = await _joined_user_ids(session, task.id)
    if len(user_ids) >= max(1, int(meta.get("min_people") or 1)):
        squad.status = "active"
        await _ensure_subtask_proposal(session, task, squad, user_ids)
    await session.flush()
    return squad


async def confirm_squad_plan(session: AsyncSession, squad: TaskSquad) -> list[TaskSubtask]:
    rows = list(
        (
            await session.scalars(
                select(TaskSubtask)
                .where(TaskSubtask.squad_id == squad.id)
                .order_by(TaskSubtask.id)
            )
        ).all()
    )
    for item in rows:
        if item.status == "proposed":
            item.status = "planned"
    squad.status = "active"
    await session.flush()
    return rows


async def assign_subtask(
    session: AsyncSession, subtask: TaskSubtask, *, assignee_id: int | None
) -> TaskSubtask:
    subtask.assignee_id = assignee_id
    if subtask.status == "proposed":
        subtask.status = "planned"
    await session.flush()
    return subtask


def _open_task_markup(settings: Settings) -> InlineKeyboardMarkup | None:
    if not settings.effective_miniapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть задачи",
                    web_app=WebAppInfo(url=settings.effective_miniapp_url),
                )
            ]
        ]
    )


async def _ensure_topic(bot: Bot, chat_id: int, task: Task, squad: TaskSquad) -> None:
    if squad.topic_id:
        return
    try:
        chat = await bot.get_chat(chat_id)
        if not bool(getattr(chat, "is_forum", False)):
            return
        topic = await bot.create_forum_topic(chat_id=chat_id, name=task.title[:128])
        squad.topic_id = topic.message_thread_id
    except TelegramAPIError:
        logger.info("Task Squad topic unavailable; using anchor replies", exc_info=True)


async def _send_squad_message(
    bot: Bot,
    settings: Settings,
    squad: TaskSquad,
    text: str,
    *,
    parse_mode: str | None = None,
    with_button: bool = False,
):
    chat_id = workspace_chat_id(settings, squad.workspace_chat_key)
    if chat_id is None:
        return None
    kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if squad.topic_id:
        kwargs["message_thread_id"] = squad.topic_id
    elif squad.anchor_message_id:
        kwargs["reply_to_message_id"] = squad.anchor_message_id
    if with_button:
        kwargs["reply_markup"] = _open_task_markup(settings)
    return await bot.send_message(**kwargs)


def _squad_card(task: Task, squad: TaskSquad, users: list[User]) -> str:
    meta = _mission_meta(task)
    names = ", ".join(
        (f"{user.first_name} {user.last_name or ''}").strip() for user in users
    ) or "команда формируется"
    responsible = next(
        (
            (f"{user.first_name} {user.last_name or ''}").strip()
            for user in users
            if user.id == squad.responsible_user_id
        ),
        "будет назначен",
    )
    checkpoint = (
        f"Ближайший чекпоинт: {_aware(squad.checkpoint_at).strftime('%d.%m · %H:%M')}\n"
        if squad.checkpoint_at
        else ""
    )
    return (
        "Новая задача · Команда сформирована\n\n"
        f"Задача: {task.title}\n"
        f"Работают: {names}\n"
        f"Ответственный: {responsible}\n"
        f"Дедлайн: {_aware(task.deadline).strftime('%d.%m · %H:%M')}\n"
        f"Результат: {meta.get('deliverable') or 'подтверждённый результат'}\n"
        f"{checkpoint}\n"
        "Работайте над задачей ответами под этой карточкой."
    )


async def _has_submission(session: AsyncSession, task_id: int) -> bool:
    return bool(
        await session.scalar(
            select(TaskSubmission.id).where(TaskSubmission.task_id == task_id)
        )
    )


async def process_task_squad_notifications(
    bot: Bot, settings: Settings, session_factory
) -> None:
    """Send only state-based Squad notices; never a daily generic reminder."""
    now = _now()
    try:
        async with session_factory() as session:
            squads = list(
                (
                    await session.scalars(
                        select(TaskSquad).where(TaskSquad.status.in_(["forming", "active"]))
                    )
                ).all()
            )
            for squad in squads:
                task = await session.get(Task, squad.task_id)
                if task is None:
                    continue
                meta = _mission_meta(task)
                user_ids = await _joined_user_ids(session, task.id)
                users = list(
                    (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()
                ) if user_ids else []
                minimum = max(1, int(meta.get("min_people") or 1))

                if len(user_ids) >= minimum and squad.anchor_message_id is None:
                    chat_id = workspace_chat_id(settings, squad.workspace_chat_key)
                    if chat_id is not None:
                        await _ensure_topic(bot, chat_id, task, squad)
                        try:
                            message = await _send_squad_message(
                                bot,
                                settings,
                                squad,
                                _squad_card(task, squad, users),
                                with_button=True,
                            )
                            if message is not None:
                                squad.anchor_message_id = message.message_id
                                squad.status = "active"
                        except TelegramAPIError:
                            logger.exception("Could not deliver Task Squad card task=%s", task.id)

                submitted = await _has_submission(session, task.id)
                responsible = (
                    await session.get(User, squad.responsible_user_id)
                    if squad.responsible_user_id
                    else None
                )
                mention = (
                    f'<a href="tg://user?id={responsible.telegram_id}">'
                    f"{html.escape(responsible.first_name)}</a>, "
                    if responsible
                    else ""
                )
                checkpoint_at = _aware(squad.checkpoint_at) if squad.checkpoint_at else None
                deadline = _aware(task.deadline)

                if (
                    checkpoint_at
                    and not submitted
                    and squad.checkpoint_notified_at is None
                    and checkpoint_at - timedelta(hours=48) <= now < checkpoint_at
                ):
                    try:
                        await _send_squad_message(
                            bot,
                            settings,
                            squad,
                            f"{mention}до чекпоинта меньше 48 часов. Зафиксируйте промежуточный результат по задаче «{html.escape(task.title)}».",
                            parse_mode="HTML",
                        )
                        squad.checkpoint_notified_at = now
                    except TelegramAPIError:
                        logger.exception("Could not send checkpoint reminder task=%s", task.id)

                if (
                    not submitted
                    and squad.deadline_notified_at is None
                    and deadline - timedelta(hours=24) <= now < deadline
                    and task.status != "completed"
                ):
                    try:
                        await _send_squad_message(
                            bot,
                            settings,
                            squad,
                            f"{mention}до дедлайна меньше 24 часов. Задача «{html.escape(task.title)}» ещё не готова.",
                            parse_mode="HTML",
                        )
                        squad.deadline_notified_at = now
                    except TelegramAPIError:
                        logger.exception("Could not send deadline reminder task=%s", task.id)

                if (
                    now >= deadline
                    and task.status != "completed"
                    and squad.overdue_notified_at is None
                ):
                    try:
                        await _send_squad_message(
                            bot,
                            settings,
                            squad,
                            f"{mention}дедлайн задачи «{html.escape(task.title)}» прошёл. Нужен новый реалистичный план или сдача результата.",
                            parse_mode="HTML",
                        )
                        squad.overdue_notified_at = now
                    except TelegramAPIError:
                        logger.exception("Could not send overdue reminder task=%s", task.id)

                if submitted and squad.submission_notified_at is None:
                    try:
                        await _send_squad_message(
                            bot, settings, squad, "Результат отправлен на проверку."
                        )
                        squad.submission_notified_at = now
                    except TelegramAPIError:
                        logger.exception("Could not send submission notice task=%s", task.id)

                if task.status == "completed" and squad.completed_notified_at is None:
                    try:
                        await _send_squad_message(bot, settings, squad, "Задача закрыта ✓")
                        squad.completed_notified_at = now
                        squad.status = "completed"
                    except TelegramAPIError:
                        logger.exception("Could not send completion notice task=%s", task.id)
            await session.commit()
    except Exception:
        logger.exception("Task Squad notification cycle failed")
