from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Project, User
from app.services.audit_service import audit
from app.services.points_service import add_points, add_portfolio_item
from app.services.project_builder import PROJECT_QUESTIONS, render_project_document
from app.utils.constants import ProjectStatus

ProjectScope = Literal["mine", "open", "proposals", "completed"]

PROJECT_DECISION_ACTIONS = ("initial_accept", "venue_approve", "revise", "postpone", "reject")
REVIEW_QUEUE_STATUSES = (
    ProjectStatus.PENDING_REVIEW,
    ProjectStatus.INITIAL_REVIEW,
    ProjectStatus.VENUE_REVIEW,
)

EDITABLE_STATUSES = {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}
DELETABLE_STATUSES = {
    ProjectStatus.DRAFT,
    ProjectStatus.NEEDS_REVISION,
    ProjectStatus.REJECTED,
    ProjectStatus.POSTPONED,
}
REVIEW_STATUSES = {
    ProjectStatus.PENDING_REVIEW,
    ProjectStatus.INITIAL_REVIEW,
    ProjectStatus.VENUE_REVIEW,
}
OPEN_STATUSES = {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}

_COLUMN_BY_QUESTION_KEY: dict[str, str] = {
    "title": "title",
    "idea": "short_description",
    "target_audience": "target_audience",
    "format": "format",
    "team": "team",
    "risks": "risks",
    "success_metrics": "expected_result",
}

QUESTION_KEYS: tuple[str, ...] = tuple(question.key for question in PROJECT_QUESTIONS)
TEAM_POST_PENDING_STATUSES = {"pending", "edited"}


@dataclass(frozen=True)
class TeamPostState:
    text: str
    status: str


def team_post_state(project: Project) -> TeamPostState | None:
    data = project.form_data or {}
    text = data.get("team_search_post")
    if not text:
        return None
    return TeamPostState(text=text, status=data.get("team_search_status", ""))


async def list_projects_with_pending_team_post(session: AsyncSession) -> list[Project]:
    candidates = await session.scalars(select(Project).where(Project.form_data.is_not(None)))
    return [
        project
        for project in candidates.all()
        if (project.form_data or {}).get("team_search_status") in TEAM_POST_PENDING_STATUSES
    ]


def prepare_team_post(project: Project) -> bool:
    data = dict(project.form_data or {})
    if not data.get("team_search_post"):
        return False
    data["team_search_status"] = "prepared"
    project.form_data = data
    return True


def edit_team_post(project: Project, text: str) -> bool:
    data = dict(project.form_data or {})
    if not data.get("team_search_post"):
        return False
    data["team_search_post"] = text
    data["team_search_status"] = "edited"
    project.form_data = data
    return True


def reject_team_post(project: Project) -> bool:
    data = dict(project.form_data or {})
    if not data.get("team_search_post"):
        return False
    data["team_search_status"] = "rejected"
    project.form_data = data
    return True


def publish_team_post(project: Project) -> str | None:
    data = dict(project.form_data or {})
    if data.get("team_search_status") != "prepared":
        return None
    text = data.get("team_search_post")
    if not text:
        return None
    data["team_search_status"] = "published"
    project.form_data = data
    return text


async def list_projects_for_user(
    session: AsyncSession, user: User, scope: ProjectScope
) -> list[Project]:
    if scope == "mine":
        rows = await session.scalars(
            select(Project)
            .where(Project.author_id == user.id, Project.status != ProjectStatus.CANCELLED)
            .order_by(Project.updated_at.desc())
        )
        return list(rows.all())
    if scope == "proposals":
        rows = await session.scalars(
            select(Project)
            .where(Project.author_id == user.id, Project.status.in_(REVIEW_STATUSES))
            .order_by(Project.submitted_at.desc())
        )
        return list(rows.all())
    if scope == "completed":
        rows = await session.scalars(
            select(Project)
            .where(Project.author_id == user.id, Project.status == ProjectStatus.COMPLETED)
            .order_by(Project.updated_at.desc())
        )
        return list(rows.all())
    rows = await session.scalars(
        select(Project)
        .where(Project.status.in_(OPEN_STATUSES))
        .order_by(Project.updated_at.desc())
    )
    return list(rows.all())


def can_edit(project: Project) -> bool:
    return project.status in EDITABLE_STATUSES


def can_submit_for_review(project: Project) -> bool:
    return project.status in EDITABLE_STATUSES


def can_delete(project: Project) -> bool:
    return project.status in DELETABLE_STATUSES


def missing_required_answers(project: Project) -> tuple[str, ...]:
    data = project.form_data or {}
    return tuple(
        question.key
        for question in PROJECT_QUESTIONS
        if not str(data.get(question.key) or "").strip()
    )


async def create_draft(session: AsyncSession, user: User, idea: str) -> Project:
    project = Project(
        author_id=user.id,
        title=(idea[:255] if idea else "Новый проект"),
        short_description=idea or "Идея формируется",
        form_data={"idea": idea} if idea else {},
        status=ProjectStatus.DRAFT,
    )
    session.add(project)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="project.draft_created",
        entity_type="project",
        entity_id=project.id,
    )
    return project


def _parse_project_date(value: str):
    cleaned = value.strip()
    if not cleaned:
        return None
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    raise ValueError("invalid_project_date")


def _parse_project_time(value: str):
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return datetime.strptime(cleaned, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("invalid_project_time") from exc


def update_answers(project: Project, answers: dict[str, str]) -> None:
    """Apply a true partial update from either Bot or Mini App.

    Date/time are first-class project fields now too. The Mini App uses ISO
    date + HH:MM inputs while the older Bot may still send DD.MM.YYYY; both
    formats are accepted and normalized in the typed Project columns.
    """
    form_data = dict(project.form_data or {})
    for key, value in answers.items():
        if key not in QUESTION_KEYS:
            continue
        if key == "proposed_date":
            parsed = _parse_project_date(value)
            project.proposed_date = parsed
            form_data[key] = parsed.isoformat() if parsed else ""
            continue
        if key == "proposed_time":
            parsed = _parse_project_time(value)
            project.proposed_time = parsed
            form_data[key] = parsed.strftime("%H:%M") if parsed else ""
            continue
        form_data[key] = value
        column = _COLUMN_BY_QUESTION_KEY.get(key)
        if column:
            setattr(project, column, value[:255] if column in {"title", "format"} else value)
    project.form_data = form_data


def project_document_text(project: Project, author: User) -> str:
    if project.generated_document:
        return project.generated_document
    author_name = f"{author.first_name} {author.last_name or ''}".strip()
    telegram = f"@{author.username}" if author.username else str(author.telegram_id)
    return render_project_document(project.form_data or {}, author_name, telegram)


async def submit_for_review(session: AsyncSession, project: Project, user: User) -> str:
    document = project_document_text(project, user)
    project.status = ProjectStatus.INITIAL_REVIEW
    project.submitted_at = datetime.now().astimezone()
    project.generated_document = document
    await audit(
        session,
        actor_id=user.id,
        action="project.submitted",
        entity_type="project",
        entity_id=project.id,
    )
    return document


async def cancel_project(session: AsyncSession, project: Project, user: User) -> None:
    project.status = ProjectStatus.CANCELLED
    await audit(
        session,
        actor_id=user.id,
        action="project.cancelled",
        entity_type="project",
        entity_id=project.id,
    )


async def list_projects_for_review(session: AsyncSession) -> list[Project]:
    rows = await session.scalars(
        select(Project)
        .where(Project.status.in_(REVIEW_QUEUE_STATUSES))
        .order_by(Project.submitted_at, Project.updated_at)
    )
    return list(rows.all())


@dataclass(frozen=True)
class ModerationResult:
    notice: str
    project: Project


async def decide_project(
    session: AsyncSession, project: Project, *, action: str, comment: str, actor: User
) -> ModerationResult:
    if action not in PROJECT_DECISION_ACTIONS:
        raise ValueError(f"unknown project decision action: {action!r}")

    old_status = project.status
    project.admin_comment = comment

    if action == "initial_accept":
        project.status = ProjectStatus.VENUE_REVIEW
        project.venue_status = "pending"
        project.venue_comment = comment
        project.venue_reminder_count = 0
        project.venue_remind_at = datetime.now().astimezone() + timedelta(days=1)
        notice = "Проект прошёл первичную проверку и перешёл к следующему этапу"
    elif action == "venue_approve":
        project.status = ProjectStatus.APPROVED
        project.venue_status = "approved"
        project.venue_comment = comment
        project.venue_remind_at = None
        if old_status != ProjectStatus.APPROVED:
            await add_points(
                session,
                user_id=project.author_id,
                points=30,
                reason=f"Одобренный проект: {project.title}",
                approved_by=actor.id,
                related_project_id=project.id,
                source_type="project_approval",
                source_id=project.id,
                idempotency_key=f"project_approval:{project.id}",
            )
            await add_portfolio_item(
                session,
                user_id=project.author_id,
                title=f"Автор проекта: {project.title}",
                item_type="project",
                description=project.short_description,
                issued_by=actor.id,
                related_project_id=project.id,
            )
        notice = "Проект одобрен. Следующий шаг — оформить мероприятие или найти команду"
    elif action == "revise":
        project.status = ProjectStatus.NEEDS_REVISION
        project.venue_remind_at = None
        notice = "Проект возвращён на доработку"
    elif action == "postpone":
        project.status = ProjectStatus.POSTPONED
        project.venue_remind_at = None
        notice = "Проект перенесён"
    else:
        project.status = ProjectStatus.REJECTED
        project.venue_remind_at = None
        notice = "Проект отклонён"

    await session.flush()
    return ModerationResult(notice=notice, project=project)
