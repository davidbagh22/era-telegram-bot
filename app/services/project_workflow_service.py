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

# Same question-key -> Project column mapping the bot's guided wizard uses
# (app/handlers/participant/projects.py::project_answer). Kept here so the
# Mini App's incremental edit stays in sync with it instead of drifting.
_COLUMN_BY_QUESTION_KEY: dict[str, str] = {
    "title": "title",
    "idea": "short_description",
    "target_audience": "target_audience",
    "format": "format",
    "team": "team",
    "risks": "risks",
    "success_metrics": "expected_result",
}

# Keep values written into typed SQL columns inside the actual schema limits.
# The constructor stores the full editorial answer in form_data, while the
# compact typed column is only a denormalized/searchable representation.
_COLUMN_MAX_LENGTH: dict[str, int] = {
    "title": 255,
    "format": 100,
}

QUESTION_KEYS: tuple[str, ...] = tuple(question.key for question in PROJECT_QUESTIONS)

# "Looking for a team" broadcast to the general chat — a project author
# writes it (app/handlers/participant/projects_block5.py::team_submit),
# then it needs admin sign-off before going out publicly. Storage is a
# couple of keys inside the existing form_data JSON blob (not a dedicated
# column) — this mirrors app/handlers/admin/projects_block5_team.py exactly
# so the bot and the Mini App read/write the identical state and can't
# drift into two different ideas of what stage a post is at. Distinct from
# ProjectWorkspace's in-app role/application system (PR5): this reaches
# people in the general Telegram chat who aren't necessarily browsing the
# Mini App at all.
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
    """Marks a pending/edited post ready to publish. False if there's no
    post to prepare."""
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
    """Returns the text to actually publish, only when it was prepared
    first — mirrors the bot's own "Сначала нажмите «Одобрить 1/2»" guard."""
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


def update_answers(project: Project, answers: dict[str, str]) -> None:
    """Apply partial question-key -> answer updates without touching other
    constructor answers. Unknown keys are ignored. Full answers stay in
    form_data; denormalized SQL columns are clipped to their real limits."""
    form_data = dict(project.form_data or {})
    for key, value in answers.items():
        if key not in QUESTION_KEYS:
            continue
        form_data[key] = value
        column = _COLUMN_BY_QUESTION_KEY.get(key)
        if column:
            max_length = _COLUMN_MAX_LENGTH.get(column)
            setattr(project, column, value[:max_length] if max_length else value)
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
    """Mirrors app/handlers/admin/projects_block5_decision.py::decision_finish
    exactly, including the old_status guard that stops points/portfolio
    credit from being awarded twice if a project is re-approved."""
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
