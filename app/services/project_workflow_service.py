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
# Mini App's single-form edit stays in sync with it instead of drifting.
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
    # "open": a directory of live ERA projects across all authors — this is
    # new (participants previously only ever saw their own projects), but it
    # is a real query with no fabricated data, and it's a prerequisite for
    # PR 5's "find a team" workspace to have anything to browse.
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
    """Apply a partial set of question-key -> answer updates, mirroring the
    Bot wizard's per-question field mapping. Unknown keys are ignored."""
    form_data = dict(project.form_data or {})
    for key, value in answers.items():
        if key not in QUESTION_KEYS:
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
    else:  # reject
        project.status = ProjectStatus.REJECTED
        project.venue_remind_at = None
        notice = "Проект отклонён"

    await session.flush()
    return ModerationResult(notice=notice, project=project)
