from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.database.models import (
    Event,
    PermissionGrant,
    Project,
    ProjectMember,
    ProjectMilestone,
    ProjectRole,
    Task,
    User,
)
from app.services.audit_service import audit
from app.services.authorization_service import is_full_admin
from app.services.notification_service import BroadcastResult, safe_send
from app.utils.constants import ProjectStatus, TaskStatus

ROLE_STATUSES = {"open", "closed"}
ACTIVE_MEMBER_STATUSES = {"accepted", "active", "completed"}
REVIEWABLE_MEMBER_STATUSES = {"pending"}
MILESTONE_STATUSES = {"pending", "in_progress", "blocked", "completed"}
OPEN_PROJECT_STATUSES = {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}


class WorkspaceError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RoleWithFill:
    role: ProjectRole
    filled: int


@dataclass(frozen=True)
class ProjectWorkspaceSnapshot:
    project: Project
    can_manage: bool
    viewer_membership_status: str | None
    roles: list[RoleWithFill]
    members: list[ProjectMember]
    milestones: list[ProjectMilestone]
    tasks: list[Task]
    events: list[Event]


def _is_active_user(user: User | None) -> bool:
    return bool(user and not user.is_blocked and not user.is_archived)


async def can_review_projects(
    session: AsyncSession, user: User | None, settings: Settings
) -> bool:
    if not _is_active_user(user):
        return False
    if is_full_admin(user, settings, user.telegram_id):
        return True
    return bool(
        await session.scalar(
            select(PermissionGrant.id).where(
                PermissionGrant.user_id == user.id,
                PermissionGrant.permission == "projects.review",
                PermissionGrant.is_active.is_(True),
            )
        )
    )


async def can_manage_project(
    session: AsyncSession, project: Project, user: User | None, settings: Settings
) -> bool:
    if not _is_active_user(user):
        return False
    return project.author_id == user.id or await can_review_projects(session, user, settings)


async def membership_for_user(
    session: AsyncSession, project_id: int, user_id: int
) -> ProjectMember | None:
    return await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )


async def can_view_workspace(
    session: AsyncSession, project: Project, user: User, settings: Settings
) -> bool:
    if await can_manage_project(session, project, user, settings):
        return True
    membership = await membership_for_user(session, project.id, user.id)
    if membership and membership.status in ACTIVE_MEMBER_STATUSES:
        return True
    return project.status in OPEN_PROJECT_STATUSES


async def require_project(
    session: AsyncSession, project_id: int, user: User, settings: Settings, *, manage: bool = False
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise WorkspaceError("project_not_found")
    allowed = (
        await can_manage_project(session, project, user, settings)
        if manage
        else await can_view_workspace(session, project, user, settings)
    )
    if not allowed:
        raise WorkspaceError("project_not_found" if not manage else "not_allowed")
    return project


def _clean_text(value: str | None, max_length: int) -> str:
    return (value or "").strip()[:max_length]


async def role_filled(session: AsyncSession, role_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.role_id == role_id,
                ProjectMember.status.in_(ACTIVE_MEMBER_STATUSES),
            )
        )
        or 0
    )


async def _ensure_role(
    session: AsyncSession, project_id: int, role_id: int | None
) -> ProjectRole | None:
    if role_id is None:
        return None
    role = await session.get(ProjectRole, role_id)
    if role is None or role.project_id != project_id:
        raise WorkspaceError("role_not_found")
    return role


async def _ensure_member(session: AsyncSession, project_id: int, member_id: int) -> ProjectMember:
    member = await session.scalar(
        select(ProjectMember)
        .options(selectinload(ProjectMember.user), selectinload(ProjectMember.role))
        .where(ProjectMember.id == member_id, ProjectMember.project_id == project_id)
    )
    if member is None:
        raise WorkspaceError("member_not_found")
    return member


async def _ensure_project_task(session: AsyncSession, project_id: int, task_id: int) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise WorkspaceError("task_not_found")
    return task


async def _ensure_active_project_member(
    session: AsyncSession, project: Project, user_id: int | None
) -> ProjectMember | None:
    if user_id is None:
        return None
    if user_id == project.author_id:
        return None
    member = await membership_for_user(session, project.id, user_id)
    if member is None or member.status not in ACTIVE_MEMBER_STATUSES:
        raise WorkspaceError("assignee_not_project_member")
    return member


async def _ensure_role_has_capacity(session: AsyncSession, role: ProjectRole | None) -> None:
    if role is None or role.capacity is None:
        return
    if await role_filled(session, role.id) >= role.capacity:
        raise WorkspaceError("role_full")


async def workspace_snapshot(
    session: AsyncSession, project: Project, user: User, settings: Settings
) -> ProjectWorkspaceSnapshot:
    roles = list(
        (
            await session.scalars(
                select(ProjectRole)
                .where(ProjectRole.project_id == project.id)
                .order_by(ProjectRole.sort_order, ProjectRole.id)
            )
        ).all()
    )
    members = list(
        (
            await session.scalars(
                select(ProjectMember)
                .options(selectinload(ProjectMember.user), selectinload(ProjectMember.role))
                .where(ProjectMember.project_id == project.id)
                .order_by(ProjectMember.created_at, ProjectMember.id)
            )
        ).all()
    )
    milestones = list(
        (
            await session.scalars(
                select(ProjectMilestone)
                .where(ProjectMilestone.project_id == project.id)
                .order_by(ProjectMilestone.sort_order, ProjectMilestone.id)
            )
        ).all()
    )
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.project_id == project.id)
                .order_by(Task.deadline, Task.id)
            )
        ).all()
    )
    events = list(
        (
            await session.scalars(
                select(Event)
                .where(Event.project_id == project.id)
                .order_by(Event.event_date, Event.event_time, Event.id)
            )
        ).all()
    )
    viewer_membership = next((item for item in members if item.user_id == user.id), None)
    fills = {role.id: await role_filled(session, role.id) for role in roles}
    return ProjectWorkspaceSnapshot(
        project=project,
        can_manage=await can_manage_project(session, project, user, settings),
        viewer_membership_status=viewer_membership.status if viewer_membership else None,
        roles=[RoleWithFill(role=role, filled=fills[role.id]) for role in roles],
        members=members,
        milestones=milestones,
        tasks=tasks,
        events=events,
    )


async def create_role(
    session: AsyncSession,
    project: Project,
    actor: User,
    *,
    title: str,
    description: str | None = None,
    requirements: str | None = None,
    capacity: int | None = None,
) -> ProjectRole:
    title = _clean_text(title, 120)
    if not title:
        raise WorkspaceError("role_title_required")
    if capacity is not None and capacity < 1:
        raise WorkspaceError("invalid_role_capacity")
    existing_role_id = await session.scalar(
        select(ProjectRole.id).where(
            ProjectRole.project_id == project.id,
            ProjectRole.title == title,
        )
    )
    if existing_role_id:
        raise WorkspaceError("role_already_exists")
    max_order = int(
        await session.scalar(
            select(func.max(ProjectRole.sort_order)).where(ProjectRole.project_id == project.id)
        )
        or 0
    )
    role = ProjectRole(
        project_id=project.id,
        title=title,
        description=_clean_text(description, 4000) or None,
        requirements=_clean_text(requirements, 4000) or None,
        capacity=capacity,
        status="open",
        created_by=actor.id,
        sort_order=max_order + 10,
    )
    session.add(role)
    await session.flush()
    await audit(
        session,
        actor_id=actor.id,
        action="project.role.created",
        entity_type="project_role",
        entity_id=role.id,
        new_value={"project_id": project.id, "title": role.title},
    )
    return role


async def set_role_status(
    session: AsyncSession, project: Project, actor: User, role_id: int, status: str
) -> ProjectRole:
    if status not in ROLE_STATUSES:
        raise WorkspaceError("invalid_role_status")
    role = await _ensure_role(session, project.id, role_id)
    assert role is not None
    old = role.status
    role.status = status
    await audit(
        session,
        actor_id=actor.id,
        action="project.role.status_changed",
        entity_type="project_role",
        entity_id=role.id,
        old_value={"status": old},
        new_value={"status": role.status},
    )
    return role


async def apply_to_role(
    session: AsyncSession,
    project: Project,
    applicant: User,
    *,
    role_id: int | None,
    application_text: str | None,
) -> ProjectMember:
    if project.status not in OPEN_PROJECT_STATUSES:
        raise WorkspaceError("project_not_open")
    role = await _ensure_role(session, project.id, role_id)
    if role is not None:
        if role.status != "open":
            raise WorkspaceError("role_closed")
        await _ensure_role_has_capacity(session, role)
    existing = await membership_for_user(session, project.id, applicant.id)
    if existing:
        if existing.status == "pending":
            raise WorkspaceError("already_pending")
        if existing.status in ACTIVE_MEMBER_STATUSES:
            raise WorkspaceError("already_member")
        existing.role_id = role.id if role else None
        existing.status = "pending"
        existing.application_text = _clean_text(application_text, 4000) or None
        await audit(
            session,
            actor_id=applicant.id,
            action="project.member.reapplied",
            entity_type="project_member",
            entity_id=existing.id,
            new_value={"project_id": project.id, "role_id": existing.role_id},
        )
        return existing
    member = ProjectMember(
        project_id=project.id,
        user_id=applicant.id,
        role_id=role.id if role else None,
        status="pending",
        application_text=_clean_text(application_text, 4000) or None,
    )
    session.add(member)
    await session.flush()
    await audit(
        session,
        actor_id=applicant.id,
        action="project.member.applied",
        entity_type="project_member",
        entity_id=member.id,
        new_value={"project_id": project.id, "role_id": member.role_id},
    )
    return member


async def add_member(
    session: AsyncSession,
    project: Project,
    actor: User,
    *,
    user_id: int,
    role_id: int | None,
) -> ProjectMember:
    target = await session.get(User, user_id)
    if target is None or target.is_blocked or target.is_archived:
        raise WorkspaceError("user_not_found")
    role = await _ensure_role(session, project.id, role_id)
    existing = await membership_for_user(session, project.id, target.id)
    if not (
        existing
        and existing.status in ACTIVE_MEMBER_STATUSES
        and existing.role_id == (role.id if role else None)
    ):
        await _ensure_role_has_capacity(session, role)
    now = datetime.now().astimezone()
    if existing:
        old_status = existing.status
        existing.role_id = role.id if role else None
        existing.status = "accepted"
        existing.joined_at = existing.joined_at or now
        existing.approved_by = actor.id
        member = existing
        old_value = {"status": old_status}
    else:
        member = ProjectMember(
            project_id=project.id,
            user_id=target.id,
            role_id=role.id if role else None,
            status="accepted",
            joined_at=now,
            approved_by=actor.id,
        )
        session.add(member)
        await session.flush()
        old_value = None
    await audit(
        session,
        actor_id=actor.id,
        action="project.member.added",
        entity_type="project_member",
        entity_id=member.id,
        old_value=old_value,
        new_value={"project_id": project.id, "user_id": target.id, "role_id": member.role_id},
    )
    return member


async def review_application(
    session: AsyncSession,
    project: Project,
    actor: User,
    member_id: int,
    *,
    approve: bool,
) -> ProjectMember:
    member = await _ensure_member(session, project.id, member_id)
    if member.status not in REVIEWABLE_MEMBER_STATUSES:
        raise WorkspaceError("application_not_pending")
    role = await _ensure_role(session, project.id, member.role_id)
    if approve:
        await _ensure_role_has_capacity(session, role)
    old = member.status
    member.status = "accepted" if approve else "rejected"
    member.approved_by = actor.id
    if approve:
        member.joined_at = datetime.now().astimezone()
    await audit(
        session,
        actor_id=actor.id,
        action="project.member.approved" if approve else "project.member.rejected",
        entity_type="project_member",
        entity_id=member.id,
        old_value={"status": old},
        new_value={"status": member.status, "project_id": project.id},
    )
    return member


async def change_member_role(
    session: AsyncSession,
    project: Project,
    actor: User,
    member_id: int,
    *,
    role_id: int | None,
) -> ProjectMember:
    member = await _ensure_member(session, project.id, member_id)
    if member.status not in ACTIVE_MEMBER_STATUSES and member.status != "pending":
        raise WorkspaceError("member_not_active")
    role = await _ensure_role(session, project.id, role_id)
    if member.role_id != (role.id if role else None):
        await _ensure_role_has_capacity(session, role)
    old = member.role_id
    member.role_id = role.id if role else None
    await audit(
        session,
        actor_id=actor.id,
        action="project.member.role_changed",
        entity_type="project_member",
        entity_id=member.id,
        old_value={"role_id": old},
        new_value={"role_id": member.role_id},
    )
    return member


async def confirm_contribution(
    session: AsyncSession,
    project: Project,
    actor: User,
    member_id: int,
    *,
    summary: str,
    result: str | None = None,
) -> ProjectMember:
    member = await _ensure_member(session, project.id, member_id)
    if member.status not in ACTIVE_MEMBER_STATUSES:
        raise WorkspaceError("member_not_active")
    summary = _clean_text(summary, 4000)
    if not summary:
        raise WorkspaceError("contribution_summary_required")
    member.contribution_status = "confirmed"
    member.contribution_summary = summary
    member.contribution_result = _clean_text(result, 4000) or None
    member.contribution_role_title = member.role.title if member.role else None
    member.contribution_confirmed_at = datetime.now().astimezone()
    member.contribution_confirmed_by = actor.id
    await audit(
        session,
        actor_id=actor.id,
        action="project.member.contribution_confirmed",
        entity_type="project_member",
        entity_id=member.id,
        new_value={
            "project_id": project.id,
            "role": member.contribution_role_title,
            "result": member.contribution_result,
        },
    )
    return member


async def create_milestone(
    session: AsyncSession,
    project: Project,
    actor: User,
    *,
    title: str,
    description: str | None = None,
    deadline: datetime | None = None,
    responsible_id: int | None = None,
) -> ProjectMilestone:
    title = _clean_text(title, 200)
    if not title:
        raise WorkspaceError("milestone_title_required")
    await _ensure_active_project_member(session, project, responsible_id)
    max_order = int(
        await session.scalar(
            select(func.max(ProjectMilestone.sort_order)).where(ProjectMilestone.project_id == project.id)
        )
        or 0
    )
    milestone = ProjectMilestone(
        project_id=project.id,
        title=title,
        description=_clean_text(description, 4000) or None,
        deadline=deadline,
        responsible_id=responsible_id,
        status="pending",
        sort_order=max_order + 10,
    )
    session.add(milestone)
    await session.flush()
    await audit(
        session,
        actor_id=actor.id,
        action="project.milestone.created",
        entity_type="project_milestone",
        entity_id=milestone.id,
        new_value={"project_id": project.id, "title": milestone.title},
    )
    return milestone


async def set_milestone_status(
    session: AsyncSession,
    project: Project,
    actor: User,
    milestone_id: int,
    *,
    status: str,
) -> ProjectMilestone:
    if status not in MILESTONE_STATUSES:
        raise WorkspaceError("invalid_milestone_status")
    milestone = await session.get(ProjectMilestone, milestone_id)
    if milestone is None or milestone.project_id != project.id:
        raise WorkspaceError("milestone_not_found")
    old = milestone.status
    milestone.status = status
    if status == "completed":
        milestone.completed_at = milestone.completed_at or datetime.now().astimezone()
        milestone.completed_by = actor.id
    elif old == "completed":
        milestone.completed_at = None
        milestone.completed_by = None
    await audit(
        session,
        actor_id=actor.id,
        action="project.milestone.status_changed",
        entity_type="project_milestone",
        entity_id=milestone.id,
        old_value={"status": old},
        new_value={"status": milestone.status, "project_id": project.id},
    )
    return milestone


async def create_project_task(
    session: AsyncSession,
    project: Project,
    actor: User,
    *,
    title: str,
    description: str,
    deadline: datetime,
    assignee_id: int | None = None,
    points: int = 10,
) -> Task:
    title = _clean_text(title, 255)
    description = _clean_text(description, 4000)
    if not title:
        raise WorkspaceError("task_title_required")
    if not description:
        raise WorkspaceError("task_description_required")
    if points < 0:
        raise WorkspaceError("invalid_task_points")
    await _ensure_active_project_member(session, project, assignee_id)
    task = Task(
        project_id=project.id,
        title=title,
        description=description,
        assignee_id=assignee_id,
        creator_id=actor.id,
        department_id=project.department_id,
        direction_id=project.direction_id,
        deadline=deadline,
        points=points,
        status=TaskStatus.NEW,
        task_type="private",
    )
    session.add(task)
    await session.flush()
    await audit(
        session,
        actor_id=actor.id,
        action="project.task.created",
        entity_type="task",
        entity_id=task.id,
        new_value={"project_id": project.id, "assignee_id": assignee_id},
    )
    return task


async def assign_project_task(
    session: AsyncSession,
    project: Project,
    actor: User,
    task_id: int,
    *,
    assignee_id: int | None,
) -> Task:
    task = await _ensure_project_task(session, project.id, task_id)
    await _ensure_active_project_member(session, project, assignee_id)
    old = task.assignee_id
    task.assignee_id = assignee_id
    await audit(
        session,
        actor_id=actor.id,
        action="project.task.assigned",
        entity_type="task",
        entity_id=task.id,
        old_value={"assignee_id": old},
        new_value={"assignee_id": task.assignee_id, "project_id": project.id},
    )
    return task


async def link_event(
    session: AsyncSession, project: Project, actor: User, event_id: int
) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise WorkspaceError("event_not_found")
    old = event.project_id
    event.project_id = project.id
    await audit(
        session,
        actor_id=actor.id,
        action="project.event.linked",
        entity_type="event",
        entity_id=event.id,
        old_value={"project_id": old},
        new_value={"project_id": project.id},
    )
    return event


async def message_team(
    session: AsyncSession,
    project: Project,
    actor: User,
    bot: Bot,
    *,
    text: str,
) -> BroadcastResult:
    text = _clean_text(text, 4000)
    if not text:
        raise WorkspaceError("message_text_required")
    members = (
        await session.scalars(
            select(ProjectMember)
            .options(selectinload(ProjectMember.user))
            .where(
                ProjectMember.project_id == project.id,
                ProjectMember.status.in_(ACTIVE_MEMBER_STATUSES),
            )
        )
    ).all()
    result = BroadcastResult(total=len(members))
    message = f"Сообщение команды проекта «{project.title}»\n\n{text}"
    for member in members:
        if await safe_send(bot, member.user.telegram_id, message):
            result.sent += 1
        else:
            result.failed += 1
    await audit(
        session,
        actor_id=actor.id,
        action="project.team.message_sent",
        entity_type="project",
        entity_id=project.id,
        new_value={"total": result.total, "sent": result.sent, "failed": result.failed},
    )
    return result
