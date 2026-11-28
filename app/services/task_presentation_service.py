from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.media_models import MediaContentItem, MediaContentTask, MediaRequest
from app.database.models import Event, Project, Task, User
from app.services import task_service
from app.services.leaders_workspace import deadline_label
from app.services.media_service import (
    MEDIA_TASK_KINDS,
    media_task_display_title,
)
from app.utils import ux_texts
from app.utils.constants import TASK_STATUS_LABELS, TaskStatus

BOT_TASKS_PAGE_SIZE = 6
_YEREVAN_TZ = ZoneInfo("Asia/Yerevan")

MEDIA_TASK_SHORT_ACTIONS: dict[str, str] = {
    "text": "Написать текст",
    "design": "Подготовить дизайн",
    "photo": "Сделать фото",
    "video": "Снять видео",
    "editing": "Смонтировать ролик",
    "stories": "Собрать сторис",
}
_ACTION_TO_MEDIA_KIND: dict[str, str] = {
    label: key for key, label in MEDIA_TASK_SHORT_ACTIONS.items()
}
_KIND_LABEL_TO_KEY: dict[str, str] = {
    **{label: key for key, label in MEDIA_TASK_KINDS.items()},
    "Stories": "stories",
}
GENERIC_MEDIA_RUBRICS = frozenset({"События ЭРА", "Проекты ЭРА", "публикации ЭРА"})

_HUMAN_MEDIA_TITLE_RE = re.compile(
    r"^(?P<action>Написать текст|Подготовить дизайн|Сделать фото|Снять видео|Смонтировать ролик|Собрать сторис)\s+для\s+«(?P<target>.+)»$"
)
_FORMULAIC_MEDIA_TITLE_RE = re.compile(
    r"^Медиа · (?P<kind>Текст|Дизайн|Фото|Видео|Монтаж|Stories|Сторис) · (?P<target>.+)$"
)
_MEDIA_PACKAGE_BODY_RE = re.compile(
    r"^Медиа-пакет для (?:event|project):\s*(?P<target>.+)$"
)


@dataclass(frozen=True)
class TaskContext:
    display_title: str
    short_title: str
    group_key: str
    group_kind: str  # "event" | "project" | "media" | "general"
    group_title: str | None
    group_date: str | None  # DD.MM.YYYY
    group_date_iso: str | None  # YYYY-MM-DD
    effective_status: str
    is_expired: bool


def _plural_ru(count: int, one: str, few: str, many: str) -> str:
    n = abs(count) % 100
    if 11 <= n <= 19:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def plural_open_tasks(count: int) -> str:
    return f"{count} {_plural_ru(count, 'открытая задача', 'открытые задачи', 'открытых задач')}"


def plural_active_tasks(count: int) -> str:
    return f"{count} {_plural_ru(count, 'задача в работе', 'задачи в работе', 'задач в работе')}"


def plural_archive_tasks(count: int) -> str:
    return f"{count} {_plural_ru(count, 'задача в архиве', 'задачи в архиве', 'задач в архиве')}"


def plural_points(points: int) -> str:
    return f"{points} {_plural_ru(points, 'балл', 'балла', 'баллов')}"


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(1, limit - 1)].rstrip()}…"


def _format_date_pair(value: date | datetime | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, datetime):
        local = (
            value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        ).astimezone(_YEREVAN_TZ)
        day = local.date()
    else:
        day = value
    return day.strftime("%d.%m.%Y"), day.isoformat()


def _extract_source_title_from_body(body: str | None) -> str | None:
    if not body:
        return None
    first_line = body.strip().splitlines()[0].strip()
    match = _MEDIA_PACKAGE_BODY_RE.match(first_line)
    if match:
        target = match.group("target").strip()
        if target and target not in GENERIC_MEDIA_RUBRICS:
            return target
    return None


def _parse_media_template_title(title: str) -> tuple[str | None, str | None, bool]:
    """Return (task_kind, target_label, is_formulaic) if title is a template media title."""
    cleaned = (title or "").strip()
    human_match = _HUMAN_MEDIA_TITLE_RE.match(cleaned)
    if human_match:
        kind = _ACTION_TO_MEDIA_KIND.get(human_match.group("action"))
        target = human_match.group("target").strip()
        return kind, target, False
    formulaic_match = _FORMULAIC_MEDIA_TITLE_RE.match(cleaned)
    if formulaic_match:
        kind = _KIND_LABEL_TO_KEY.get(formulaic_match.group("kind"))
        target = formulaic_match.group("target").strip()
        return kind, target, True
    return None, None, False


def task_status_label(
    task: Task, *, completed: bool = False, now: datetime | None = None
) -> str:
    if completed:
        return "Выполнено"
    status = task_service.effective_task_status(task, completed=False, now=now)
    return TASK_STATUS_LABELS.get(status, status)


def _supports_db_queries(session: AsyncSession | None) -> bool:
    return bool(session is not None and hasattr(session, "scalars") and hasattr(session, "execute"))


async def resolve_task_contexts(
    session: AsyncSession | None,
    tasks: Sequence[Task],
    *,
    completed_ids: set[int] | None = None,
    now: datetime | None = None,
) -> dict[int, TaskContext]:
    """Batch-resolve real event/project context, human titles, and deadline status."""
    completed_set = completed_ids or set()
    if not tasks:
        return {}

    current = now or datetime.now(timezone.utc)
    media_task_ids: list[int] = []
    reward_content_ids: set[int] = set()
    project_ids: set[int] = set()
    event_ids: set[int] = set()

    for task in tasks:
        reward = getattr(task, "reward_json", None) or {}
        if getattr(task, "project_id", None):
            project_ids.add(int(task.project_id))
        if reward.get("media_task") or _parse_media_template_title(getattr(task, "title", ""))[0]:
            if getattr(task, "id", None) is not None:
                media_task_ids.append(task.id)
        if reward.get("media_content_id"):
            reward_content_ids.add(int(reward["media_content_id"]))
        if reward.get("source_type") == "event" and reward.get("source_id"):
            event_ids.add(int(reward["source_id"]))
        elif reward.get("source_type") == "project" and reward.get("source_id"):
            project_ids.add(int(reward["source_id"]))

    media_links_by_task: dict[int, MediaContentTask] = {}
    content_by_id: dict[int, MediaContentItem] = {}
    request_by_content: dict[int, MediaRequest] = {}
    events_by_id: dict[int, Event] = {}
    projects_by_id: dict[int, Project] = {}

    if _supports_db_queries(session) and (media_task_ids or reward_content_ids or project_ids or event_ids):
        if media_task_ids:
            links = (
                await session.scalars(
                    select(MediaContentTask).where(MediaContentTask.task_id.in_(media_task_ids))
                )
            ).all()
            for link in links:
                media_links_by_task[link.task_id] = link
                reward_content_ids.add(link.content_id)

        if reward_content_ids:
            items = (
                await session.scalars(
                    select(MediaContentItem).where(MediaContentItem.id.in_(reward_content_ids))
                )
            ).all()
            for item in items:
                content_by_id[item.id] = item
                if item.source_type == "event" and item.source_id:
                    event_ids.add(int(item.source_id))
                elif item.source_type == "project" and item.source_id:
                    project_ids.add(int(item.source_id))

            requests = (
                await session.scalars(
                    select(MediaRequest).where(MediaRequest.content_id.in_(reward_content_ids))
                )
            ).all()
            for req in requests:
                if req.content_id is not None:
                    request_by_content[req.content_id] = req
                if req.source_type == "event" and req.source_id:
                    event_ids.add(int(req.source_id))
                elif req.source_type == "project" and req.source_id:
                    project_ids.add(int(req.source_id))

        if event_ids:
            events = (
                await session.scalars(select(Event).where(Event.id.in_(event_ids)))
            ).all()
            events_by_id = {event.id: event for event in events}

        if project_ids:
            projects = (
                await session.scalars(select(Project).where(Project.id.in_(project_ids)))
            ).all()
            projects_by_id = {project.id: project for project in projects}

    contexts: dict[int, TaskContext] = {}
    for task in tasks:
        reward = getattr(task, "reward_json", None) or {}
        link = media_links_by_task.get(task.id)
        content_id = link.content_id if link else reward.get("media_content_id")
        content = content_by_id.get(int(content_id)) if content_id is not None else None
        req = request_by_content.get(int(content_id)) if content_id is not None else None

        group_kind = "general"
        group_key = "general"
        group_title: str | None = None
        group_date: str | None = None
        group_date_iso: str | None = None

        source_type = (
            (content.source_type if content and content.source_type else None)
            or (req.source_type if req and req.source_type else None)
            or reward.get("source_type")
        )
        source_id = (
            (content.source_id if content and content.source_id else None)
            or (req.source_id if req and req.source_id else None)
            or reward.get("source_id")
        )

        if source_type == "event" and source_id is not None:
            event = events_by_id.get(int(source_id))
            group_kind = "event"
            group_key = f"event:{int(source_id)}"
            if event is not None:
                group_title = (event.title or "").strip() or None
                group_date, group_date_iso = _format_date_pair(event.event_date)
        elif source_type == "project" and source_id is not None:
            project = projects_by_id.get(int(source_id))
            group_kind = "project"
            group_key = f"project:{int(source_id)}"
            if project is not None:
                group_title = (project.title or "").strip() or None
                group_date, group_date_iso = _format_date_pair(
                    getattr(project, "proposed_date", None)
                )
        elif getattr(task, "project_id", None):
            project = projects_by_id.get(int(task.project_id))
            group_kind = "project"
            group_key = f"project:{int(task.project_id)}"
            if project is not None:
                group_title = (project.title or "").strip() or None
                group_date, group_date_iso = _format_date_pair(
                    getattr(project, "proposed_date", None)
                )

        if not group_title and req is not None:
            req_title = str((req.metadata_json or {}).get("source_title") or "").strip()
            if req_title and req_title not in GENERIC_MEDIA_RUBRICS:
                group_title = req_title
        if not group_title and reward.get("source_title"):
            reward_title = str(reward["source_title"]).strip()
            if reward_title and reward_title not in GENERIC_MEDIA_RUBRICS:
                group_title = reward_title
        if not group_title and content is not None:
            candidate = (
                (content.title or "").strip()
                or (_extract_source_title_from_body(content.body) or "")
                or (
                    content.rubric.strip()
                    if content.rubric and content.rubric.strip() not in GENERIC_MEDIA_RUBRICS
                    else ""
                )
            )
            if candidate:
                group_title = candidate
                if group_kind == "general":
                    group_kind = "media"
                    group_key = f"media_content:{content.id}"
            elif group_kind == "general" and content.id is not None:
                group_key = "general"

        if group_date is None and content is not None and content.scheduled_at is not None and group_kind != "general":
            group_date, group_date_iso = _format_date_pair(content.scheduled_at)

        raw_title = (getattr(task, "title", "") or "").strip()
        parsed_kind, parsed_target, is_formulaic = _parse_media_template_title(raw_title)
        media_kind = (
            (link.task_kind if link else None)
            or reward.get("media_task_kind")
            or parsed_kind
        )
        if media_kind not in MEDIA_TASK_SHORT_ACTIONS:
            media_kind = parsed_kind

        display_title = raw_title
        short_title = raw_title
        if media_kind and media_kind in MEDIA_TASK_SHORT_ACTIONS and (parsed_kind or is_formulaic):
            if group_title and (parsed_target in GENERIC_MEDIA_RUBRICS or is_formulaic):
                display_title = media_task_display_title(media_kind, group_title)
            elif is_formulaic:
                display_title = media_task_display_title(media_kind, parsed_target)
            if group_title and (
                parsed_target in GENERIC_MEDIA_RUBRICS
                or parsed_target == group_title
                or is_formulaic
            ):
                short_title = MEDIA_TASK_SHORT_ACTIONS[media_kind]

        expired = task_service.is_task_expired(task, now=current)
        eff_status = task_service.effective_task_status(
            task, completed=(task.id in completed_set), now=current
        )
        contexts[task.id] = TaskContext(
            display_title=display_title,
            short_title=short_title,
            group_key=group_key,
            group_kind=group_kind,
            group_title=group_title,
            group_date=group_date,
            group_date_iso=group_date_iso,
            effective_status=eff_status,
            is_expired=expired,
        )

    return contexts


def _deadline_sort_key(deadline: datetime | None) -> tuple[int, str]:
    if deadline is None:
        return (1, "9999-99-99T99:99:99")
    utc_val = deadline.replace(tzinfo=timezone.utc) if deadline.tzinfo is None else deadline.astimezone(timezone.utc)
    return (0, utc_val.isoformat())


def sort_tasks_for_display(
    tasks: Sequence[Task], contexts: dict[int, TaskContext]
) -> list[Task]:
    """Keep tasks for the same event/project together, ordered chronologically."""
    if not tasks:
        return []

    earliest_by_group: dict[str, tuple[int, str]] = {}
    for task in tasks:
        ctx = contexts[task.id]
        if ctx.group_date_iso:
            candidate = (0, ctx.group_date_iso)
        else:
            candidate = _deadline_sort_key(task.deadline)
        current = earliest_by_group.get(ctx.group_key)
        if current is None or candidate < current:
            earliest_by_group[ctx.group_key] = candidate

    def sort_key(task: Task) -> tuple:
        ctx = contexts[task.id]
        is_general = 1 if ctx.group_kind == "general" else 0
        group_order = earliest_by_group[ctx.group_key]
        group_name = (ctx.group_title or "").casefold()
        return (
            is_general,
            group_order,
            group_name,
            ctx.group_key,
            _deadline_sort_key(task.deadline),
            task.id,
        )

    return sorted(tasks, key=sort_key)


def group_heading(ctx: TaskContext) -> str:
    if ctx.group_kind == "event":
        icon = "📅"
        title = ctx.group_title or "Событие"
    elif ctx.group_kind == "project":
        icon = "💡"
        title = ctx.group_title or "Проект"
    elif ctx.group_kind == "media":
        icon = "🎬"
        title = ctx.group_title or "Медиа"
    else:
        return "📌 Общие задачи"
    if ctx.group_date:
        return f"{icon} {_truncate(title, 56)} · {ctx.group_date}"
    return f"{icon} {_truncate(title, 64)}"


def _deadline_inline(deadline: datetime | None) -> str:
    if deadline is None:
        return "без срока"
    return f"до {deadline_label(deadline, '%d.%m.%Y')}"


async def load_user_task_buckets(
    session: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, list[Task]], set[int], set[int]]:
    current = now or datetime.now(timezone.utc)
    all_tasks = await task_service.list_for_user(session, user)
    joined_ids = await task_service.joined_task_ids(session, user, all_tasks)
    completed_ids = await task_service.completed_task_ids(session, user, all_tasks)
    participated_ids = joined_ids | completed_ids

    open_tasks = [
        task
        for task in all_tasks
        if task.id not in completed_ids
        and task_service.is_open_public_task(task, participated_ids, user, now=current)
    ]
    active_tasks = [
        task
        for task in all_tasks
        if task.status not in task_service.ARCHIVE_STATUSES
        and task_service.is_joined_or_assigned(task, joined_ids, user)
    ]
    archive_tasks = [
        task
        for task in all_tasks
        if (
            task.status in task_service.ARCHIVE_STATUSES
            and task_service.is_joined_or_assigned(task, joined_ids, user)
        )
        or task.id in completed_ids
    ]
    return (
        {"open": open_tasks, "active": active_tasks, "archive": archive_tasks},
        joined_ids,
        completed_ids,
    )


def render_bot_task_list_page(
    mode: str,
    tasks: Sequence[Task],
    *,
    counts: dict[str, int],
    contexts: dict[int, TaskContext],
    joined_ids: set[int],
    completed_ids: set[int],
    page: int = 0,
    page_size: int = BOT_TASKS_PAGE_SIZE,
    now: datetime | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    ordered = sort_tasks_for_display(tasks, contexts)
    total = len(ordered)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    safe_page = max(0, min(page, total_pages - 1))

    if mode == "archive":
        heading = "🗂 Архив задач"
        summary = plural_archive_tasks(total)
        empty = ux_texts.TASKS_EMPTY_ARCHIVE
    elif mode == "active":
        heading = "🟢 Задачи в работе"
        summary = plural_active_tasks(total)
        empty = ux_texts.TASKS_EMPTY_ACTIVE
    else:
        heading = "✅ Открытые задачи"
        summary = plural_open_tasks(total)
        empty = "Сейчас нет открытых задач. Новые появятся здесь, когда команда опубликует набор."

    page_suffix = f" · стр. {safe_page + 1}/{total_pages}" if total_pages > 1 else ""
    header = f"{heading}\n{summary}{page_suffix}"

    rows: list[list[InlineKeyboardButton]] = []
    if total == 0:
        text = f"{header}\n\n{empty}"
    else:
        start = safe_page * page_size
        page_tasks = ordered[start : start + page_size]
        has_named_groups = any(
            contexts[task.id].group_kind != "general" and contexts[task.id].group_title
            for task in page_tasks
        )
        lines: list[str] = [header]
        current_group: str | None = None
        for idx, task in enumerate(page_tasks, start=1):
            ctx = contexts[task.id]
            if has_named_groups and ctx.group_key != current_group:
                lines.append("")
                lines.append(group_heading(ctx))
                current_group = ctx.group_key
            elif not has_named_groups and idx == 1:
                lines.append("")

            label = _truncate(
                ctx.short_title if has_named_groups and ctx.group_kind != "general" else ctx.display_title,
                96,
            )
            deadline_part = _deadline_inline(task.deadline)
            points_part = plural_points(task.points)
            if mode == "open":
                lines.append(f"{idx}. {label} — {deadline_part} · {points_part}")
            else:
                status_text = task_status_label(
                    task, completed=(task.id in completed_ids), now=now
                )
                lines.append(
                    f"{idx}. {label} — {status_text}, {deadline_part} · {points_part}"
                )

            can_join = (
                mode == "open"
                and task.id not in joined_ids
                and task.id not in completed_ids
                and ctx.effective_status == TaskStatus.PUBLISHED
            )
            if can_join:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"{idx}. Подробнее",
                            callback_data=f"task:view:{task.id}",
                        ),
                        InlineKeyboardButton(
                            text="🙌 Взять",
                            callback_data=f"task:join:{task.id}",
                        ),
                    ]
                )
            else:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"{idx}. Подробнее · {_truncate(label, 24)}",
                            callback_data=f"task:view:{task.id}",
                        )
                    ]
                )
        text = "\n".join(lines)

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if safe_page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=f"tasks:list:{mode}:page:{safe_page - 1}",
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"{safe_page + 1} / {total_pages}",
                callback_data="tasks:noop",
            )
        )
        if safe_page + 1 < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text="Вперёд →",
                    callback_data=f"tasks:list:{mode}:page:{safe_page + 1}",
                )
            )
        rows.append(nav_row)

    switcher: list[InlineKeyboardButton] = []
    if mode != "open":
        open_n = counts.get("open", 0)
        switcher.append(
            InlineKeyboardButton(
                text=f"🌐 Открытые · {open_n}" if open_n else "🌐 Открытые",
                callback_data="tasks:list:open",
            )
        )
    if mode != "active":
        active_n = counts.get("active", 0)
        switcher.append(
            InlineKeyboardButton(
                text=f"🟢 В работе · {active_n}" if active_n else "🟢 В работе",
                callback_data="tasks:list:active",
            )
        )
    if mode != "archive":
        archive_n = counts.get("archive", 0)
        switcher.append(
            InlineKeyboardButton(
                text=f"🗂 Архив · {archive_n}" if archive_n else "🗂 Архив",
                callback_data="tasks:list:archive",
            )
        )
    if switcher:
        rows.append(switcher)

    rows.append([InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def render_user_tasks_view(
    session: AsyncSession,
    user: User,
    *,
    mode: str = "open",
    page: int = 0,
    page_size: int = BOT_TASKS_PAGE_SIZE,
    now: datetime | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    current = now or datetime.now(timezone.utc)
    buckets, joined_ids, completed_ids = await load_user_task_buckets(
        session, user, now=current
    )
    selected = buckets.get(mode, buckets["open"])
    contexts = await resolve_task_contexts(
        session, selected, completed_ids=completed_ids, now=current
    )
    counts = {key: len(items) for key, items in buckets.items()}
    return render_bot_task_list_page(
        mode,
        selected,
        counts=counts,
        contexts=contexts,
        joined_ids=joined_ids,
        completed_ids=completed_ids,
        page=page,
        page_size=page_size,
        now=current,
    )
