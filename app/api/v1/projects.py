from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Literal

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Event, Project, ProjectMember, ProjectMilestone, ProjectRole, Task, User
from app.services import project_workflow_service, project_workspace_service
from app.services.notification_service import safe_send, safe_send_document
from app.services.project_builder import PROJECT_QUESTIONS
from app.services.project_workflow_service import ProjectScope
from app.services.project_workspace_service import WorkspaceError
from app.utils.deep_links import (
    miniapp_admin_project_url,
    miniapp_path_url,
    miniapp_project_application_url,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectQuestionOut(BaseModel):
    key: str
    block: str
    title: str
    prompt: str


# proposed_date/proposed_time are typed Project columns the Bot wizard
# parses specially (see app/handlers/participant/projects.py::project_answer);
# project_workflow_service.update_answers only stores plain strings, so
# these two stay Bot-only for now rather than silently not working right.
_EDITABLE_QUESTIONS = [q for q in PROJECT_QUESTIONS if q.input_type == "text"]


class ProjectSummaryOut(BaseModel):
    id: int
    title: str
    short_description: str
    status: str
    author_id: int
    updated_at: str
    submitted_at: str | None
    admin_comment: str | None


class ProjectDetailOut(ProjectSummaryOut):
    form_data: dict[str, str]
    can_edit: bool
    can_submit: bool
    can_delete: bool


class CreateProjectIn(BaseModel):
    idea: str = ""


class UpdateAnswersIn(BaseModel):
    answers: dict[str, str]


class RoleCreateIn(BaseModel):
    title: str
    description: str | None = None
    requirements: str | None = None
    capacity: int | None = None


class RoleStatusIn(BaseModel):
    status: Literal["open", "closed"]


class ApplicationCreateIn(BaseModel):
    role_id: int | None = None
    text: str | None = None


class AddMemberIn(BaseModel):
    user_id: int
    role_id: int | None = None


class ChangeMemberRoleIn(BaseModel):
    role_id: int | None = None


class ContributionConfirmIn(BaseModel):
    summary: str
    result: str | None = None


class MilestoneCreateIn(BaseModel):
    title: str
    description: str | None = None
    deadline: datetime | None = None
    responsible_id: int | None = None


class MilestoneStatusIn(BaseModel):
    status: Literal["pending", "in_progress", "blocked", "completed"]


class ProjectTaskCreateIn(BaseModel):
    title: str
    description: str
    deadline: datetime
    assignee_id: int | None = None
    points: int = 10


class TaskAssignIn(BaseModel):
    assignee_id: int | None = None


class TeamMessageIn(BaseModel):
    text: str


class ProjectRoleOut(BaseModel):
    id: int
    title: str
    description: str | None
    requirements: str | None
    capacity: int | None
    status: str
    filled: int
    sort_order: int


class ProjectMemberOut(BaseModel):
    id: int
    user_id: int
    full_name: str
    username: str | None
    role_id: int | None
    role_title: str | None
    status: str
    application_text: str | None
    joined_at: str | None
    approved_by: int | None
    contribution_status: str
    contribution_summary: str | None
    contribution_role_title: str | None
    contribution_result: str | None
    contribution_confirmed_at: str | None
    contribution_confirmed_by: int | None


class ProjectMilestoneOut(BaseModel):
    id: int
    title: str
    description: str | None
    sort_order: int
    deadline: str | None
    responsible_id: int | None
    status: str
    completed_at: str | None
    completed_by: int | None


class ProjectTaskOut(BaseModel):
    id: int
    title: str
    description: str
    assignee_id: int | None
    deadline: str
    points: int
    status: str
    task_type: str


class ProjectEventOut(BaseModel):
    id: int
    title: str
    event_date: str
    event_time: str
    status: str


class ProjectWorkspaceOut(BaseModel):
    project: ProjectSummaryOut
    can_manage: bool
    viewer_membership_status: str | None
    progress_percent: int
    roles: list[ProjectRoleOut]
    members: list[ProjectMemberOut]
    milestones: list[ProjectMilestoneOut]
    tasks: list[ProjectTaskOut]
    events: list[ProjectEventOut]


class TeamMessageOut(BaseModel):
    total: int
    sent: int
    failed: int


def _to_summary(project: Project) -> ProjectSummaryOut:
    return ProjectSummaryOut(
        id=project.id,
        title=project.title,
        short_description=project.short_description,
        status=project.status,
        author_id=project.author_id,
        updated_at=project.updated_at.isoformat(),
        submitted_at=project.submitted_at.isoformat() if project.submitted_at else None,
        admin_comment=project.admin_comment,
    )


def _to_detail(project: Project) -> ProjectDetailOut:
    summary = _to_summary(project)
    return ProjectDetailOut(
        **summary.model_dump(),
        form_data=project.form_data or {},
        can_edit=project_workflow_service.can_edit(project),
        can_submit=project_workflow_service.can_submit_for_review(project),
        can_delete=project_workflow_service.can_delete(project),
    )


def _visible_to(project: Project, user: User) -> bool:
    return project.author_id == user.id or project.status in project_workflow_service.OPEN_STATUSES


async def _commit_if_possible(session: AsyncSession) -> None:
    commit = getattr(session, "commit", None)
    if commit is not None:
        await commit()


def _workspace_http_error(exc: WorkspaceError) -> HTTPException:
    if exc.code in {
        "project_not_found",
        "role_not_found",
        "member_not_found",
        "task_not_found",
        "event_not_found",
        "user_not_found",
        "milestone_not_found",
    }:
        return HTTPException(status_code=404, detail=exc.code)
    if exc.code == "not_allowed":
        return HTTPException(status_code=403, detail=exc.code)
    return HTTPException(status_code=409, detail=exc.code)


async def _workspace_project(
    session: AsyncSession,
    project_id: int,
    user: User,
    settings: Settings,
    *,
    manage: bool = False,
) -> Project:
    try:
        return await project_workspace_service.require_project(
            session, project_id, user, settings, manage=manage
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


def _to_role_out(role: ProjectRole, filled: int) -> ProjectRoleOut:
    return ProjectRoleOut(
        id=role.id,
        title=role.title,
        description=role.description,
        requirements=role.requirements,
        capacity=role.capacity,
        status=role.status,
        filled=filled,
        sort_order=role.sort_order,
    )


def _to_member_out(member: ProjectMember) -> ProjectMemberOut:
    full_name = f"{member.user.first_name} {member.user.last_name or ''}".strip()
    return ProjectMemberOut(
        id=member.id,
        user_id=member.user_id,
        full_name=full_name,
        username=member.user.username,
        role_id=member.role_id,
        role_title=member.role.title if member.role else None,
        status=member.status,
        application_text=member.application_text,
        joined_at=member.joined_at.isoformat() if member.joined_at else None,
        approved_by=member.approved_by,
        contribution_status=member.contribution_status,
        contribution_summary=member.contribution_summary,
        contribution_role_title=member.contribution_role_title,
        contribution_result=member.contribution_result,
        contribution_confirmed_at=(
            member.contribution_confirmed_at.isoformat()
            if member.contribution_confirmed_at
            else None
        ),
        contribution_confirmed_by=member.contribution_confirmed_by,
    )


def _to_milestone_out(milestone: ProjectMilestone) -> ProjectMilestoneOut:
    return ProjectMilestoneOut(
        id=milestone.id,
        title=milestone.title,
        description=milestone.description,
        sort_order=milestone.sort_order,
        deadline=milestone.deadline.isoformat() if milestone.deadline else None,
        responsible_id=milestone.responsible_id,
        status=milestone.status,
        completed_at=milestone.completed_at.isoformat() if milestone.completed_at else None,
        completed_by=milestone.completed_by,
    )


def _to_project_task_out(task: Task) -> ProjectTaskOut:
    return ProjectTaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        assignee_id=task.assignee_id,
        deadline=task.deadline.isoformat(),
        points=task.points,
        status=task.status,
        task_type=task.task_type,
    )


def _to_project_event_out(event: Event) -> ProjectEventOut:
    return ProjectEventOut(
        id=event.id,
        title=event.title,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(timespec="minutes"),
        status=event.status,
    )


def _progress_percent(milestones: list[ProjectMilestoneOut]) -> int:
    if not milestones:
        return 0
    done = sum(1 for milestone in milestones if milestone.status == "completed")
    return round(done / len(milestones) * 100)


async def _to_workspace_out(
    session: AsyncSession, project: Project, user: User, settings: Settings
) -> ProjectWorkspaceOut:
    snapshot = await project_workspace_service.workspace_snapshot(session, project, user, settings)
    milestones = [_to_milestone_out(item) for item in snapshot.milestones]
    return ProjectWorkspaceOut(
        project=_to_summary(snapshot.project),
        can_manage=snapshot.can_manage,
        viewer_membership_status=snapshot.viewer_membership_status,
        progress_percent=_progress_percent(milestones),
        roles=[_to_role_out(item.role, item.filled) for item in snapshot.roles],
        members=[_to_member_out(item) for item in snapshot.members],
        milestones=milestones,
        tasks=[_to_project_task_out(item) for item in snapshot.tasks],
        events=[_to_project_event_out(item) for item in snapshot.events],
    )


@router.get("", response_model=list[ProjectSummaryOut])
async def read_projects(
    scope: ProjectScope = Query("mine"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectSummaryOut]:
    projects = await project_workflow_service.list_projects_for_user(session, user, scope)
    return [_to_summary(project) for project in projects]


@router.get("/questions", response_model=list[ProjectQuestionOut])
async def read_project_questions() -> list[ProjectQuestionOut]:
    return [
        ProjectQuestionOut(key=q.key, block=q.block, title=q.title, prompt=q.prompt)
        for q in _EDITABLE_QUESTIONS
    ]


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def read_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or not _visible_to(project, user):
        raise HTTPException(status_code=404, detail="project_not_found")
    return _to_detail(project)


@router.get("/{project_id}/workspace", response_model=ProjectWorkspaceOut)
async def read_project_workspace(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectWorkspaceOut:
    project = await _workspace_project(session, project_id, user, settings)
    return await _to_workspace_out(session, project, user, settings)


@router.post("/{project_id}/workspace/roles", response_model=ProjectRoleOut)
async def create_project_role(
    project_id: int,
    payload: RoleCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectRoleOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        role = await project_workspace_service.create_role(
            session,
            project,
            user,
            title=payload.title,
            description=payload.description,
            requirements=payload.requirements,
            capacity=payload.capacity,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    return _to_role_out(role, filled=0)


@router.patch("/{project_id}/workspace/roles/{role_id}", response_model=ProjectRoleOut)
async def update_project_role_status(
    project_id: int,
    role_id: int,
    payload: RoleStatusIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectRoleOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        role = await project_workspace_service.set_role_status(
            session, project, user, role_id, payload.status
        )
        filled = await project_workspace_service.role_filled(session, role.id)
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    return _to_role_out(role, filled=filled)


@router.post("/{project_id}/workspace/applications", response_model=ProjectMemberOut)
async def apply_to_project_role(
    project_id: int,
    payload: ApplicationCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> ProjectMemberOut:
    project = await _workspace_project(session, project_id, user, settings)
    try:
        member = await project_workspace_service.apply_to_role(
            session,
            project,
            user,
            role_id=payload.role_id,
            application_text=payload.text,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    if bot is not None:
        await _notify_project_application(bot, settings, session, project, user, member)
    workspace = await _to_workspace_out(session, project, user, settings)
    return next(item for item in workspace.members if item.id == member.id)


@router.post(
    "/{project_id}/workspace/applications/{member_id}/approve",
    response_model=ProjectMemberOut,
)
async def approve_project_application(
    project_id: int,
    member_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMemberOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        member = await project_workspace_service.review_application(
            session, project, user, member_id, approve=True
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    workspace = await _to_workspace_out(session, project, user, settings)
    return next(item for item in workspace.members if item.id == member.id)


@router.post(
    "/{project_id}/workspace/applications/{member_id}/reject",
    response_model=ProjectMemberOut,
)
async def reject_project_application(
    project_id: int,
    member_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMemberOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        member = await project_workspace_service.review_application(
            session, project, user, member_id, approve=False
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    workspace = await _to_workspace_out(session, project, user, settings)
    return next(item for item in workspace.members if item.id == member.id)


@router.post("/{project_id}/workspace/members", response_model=ProjectMemberOut)
async def add_project_member(
    project_id: int,
    payload: AddMemberIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMemberOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        member = await project_workspace_service.add_member(
            session,
            project,
            user,
            user_id=payload.user_id,
            role_id=payload.role_id,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    workspace = await _to_workspace_out(session, project, user, settings)
    return next(item for item in workspace.members if item.id == member.id)


@router.patch("/{project_id}/workspace/members/{member_id}", response_model=ProjectMemberOut)
async def change_project_member_role(
    project_id: int,
    member_id: int,
    payload: ChangeMemberRoleIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMemberOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        member = await project_workspace_service.change_member_role(
            session,
            project,
            user,
            member_id,
            role_id=payload.role_id,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    workspace = await _to_workspace_out(session, project, user, settings)
    return next(item for item in workspace.members if item.id == member.id)


@router.post(
    "/{project_id}/workspace/members/{member_id}/contribution/confirm",
    response_model=ProjectMemberOut,
)
async def confirm_project_member_contribution(
    project_id: int,
    member_id: int,
    payload: ContributionConfirmIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMemberOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        member = await project_workspace_service.confirm_contribution(
            session,
            project,
            user,
            member_id,
            summary=payload.summary,
            result=payload.result,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    workspace = await _to_workspace_out(session, project, user, settings)
    return next(item for item in workspace.members if item.id == member.id)


@router.post("/{project_id}/workspace/milestones", response_model=ProjectMilestoneOut)
async def create_project_milestone(
    project_id: int,
    payload: MilestoneCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMilestoneOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        milestone = await project_workspace_service.create_milestone(
            session,
            project,
            user,
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            responsible_id=payload.responsible_id,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    return _to_milestone_out(milestone)


@router.patch(
    "/{project_id}/workspace/milestones/{milestone_id}",
    response_model=ProjectMilestoneOut,
)
async def update_project_milestone_status(
    project_id: int,
    milestone_id: int,
    payload: MilestoneStatusIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectMilestoneOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        milestone = await project_workspace_service.set_milestone_status(
            session,
            project,
            user,
            milestone_id,
            status=payload.status,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    return _to_milestone_out(milestone)


@router.post("/{project_id}/workspace/tasks", response_model=ProjectTaskOut)
async def create_project_workspace_task(
    project_id: int,
    payload: ProjectTaskCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> ProjectTaskOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        task = await project_workspace_service.create_project_task(
            session,
            project,
            user,
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            assignee_id=payload.assignee_id,
            points=payload.points,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    if bot is not None and task.assignee_id:
        await _notify_task_assignee(bot, settings, session, project, task)
    return _to_project_task_out(task)


@router.post("/{project_id}/workspace/tasks/{task_id}/assign", response_model=ProjectTaskOut)
async def assign_project_workspace_task(
    project_id: int,
    task_id: int,
    payload: TaskAssignIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> ProjectTaskOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        task = await project_workspace_service.assign_project_task(
            session,
            project,
            user,
            task_id,
            assignee_id=payload.assignee_id,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    if bot is not None and task.assignee_id:
        await _notify_task_assignee(bot, settings, session, project, task)
    return _to_project_task_out(task)


@router.post("/{project_id}/workspace/events/{event_id}/link", response_model=ProjectEventOut)
async def link_project_workspace_event(
    project_id: int,
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectEventOut:
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        event = await project_workspace_service.link_event(session, project, user, event_id)
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    return _to_project_event_out(event)


@router.post("/{project_id}/workspace/team/message", response_model=TeamMessageOut)
async def message_project_team(
    project_id: int,
    payload: TeamMessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> TeamMessageOut:
    if bot is None:
        raise HTTPException(status_code=409, detail="bot_not_available")
    project = await _workspace_project(session, project_id, user, settings, manage=True)
    try:
        result = await project_workspace_service.message_team(
            session, project, user, bot, text=payload.text
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    await _commit_if_possible(session)
    return TeamMessageOut(total=result.total, sent=result.sent, failed=result.failed)


@router.post("", response_model=ProjectDetailOut)
async def create_project(
    payload: CreateProjectIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await project_workflow_service.create_draft(session, user, payload.idea)
    await _commit_if_possible(session)
    return _to_detail(project)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
async def update_project(
    project_id: int,
    payload: UpdateAnswersIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.can_edit(project):
        raise HTTPException(status_code=409, detail="project_not_editable")
    project_workflow_service.update_answers(project, payload.answers)
    await _commit_if_possible(session)
    return _to_detail(project)


@router.post("/{project_id}/submit", response_model=ProjectDetailOut)
async def submit_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.can_submit_for_review(project):
        raise HTTPException(status_code=409, detail="project_not_submittable")
    document = await project_workflow_service.submit_for_review(session, project, user)
    await _commit_if_possible(session)
    if bot is not None:
        await _notify_reviewers(bot, settings, project, user, document)
    return _to_detail(project)


@router.post("/{project_id}/cancel", response_model=ProjectDetailOut)
async def cancel_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.can_delete(project):
        raise HTTPException(status_code=409, detail="project_not_cancellable")
    await project_workflow_service.cancel_project(session, project, user)
    await _commit_if_possible(session)
    return _to_detail(project)


def _url_keyboard(text: str, url: str) -> InlineKeyboardMarkup | None:
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]]
    )


async def _notify_project_application(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    project: Project,
    applicant: User,
    member: ProjectMember,
) -> None:
    author = await session.get(User, project.author_id)
    if author is None:
        return
    full_name = f"{applicant.first_name} {applicant.last_name or ''}".strip()
    url = miniapp_project_application_url(settings.effective_miniapp_url, project.id, member.id)
    await safe_send(
        bot,
        author.telegram_id,
        f"В проект поступила новая заявка\n\nПроект: {project.title}\nУчастник: {full_name}",
        reply_markup=_url_keyboard("Рассмотреть заявку", url),
    )


async def _notify_task_assignee(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    project: Project,
    task: Task,
) -> None:
    if not task.assignee_id:
        return
    assignee = await session.get(User, task.assignee_id)
    if assignee is None:
        return
    url = miniapp_path_url(
        settings.effective_miniapp_url,
        f"projects/{project.id}/tasks/{task.id}",
    )
    await safe_send(
        bot,
        assignee.telegram_id,
        f"Вам назначена задача по проекту «{project.title}»\n\n{task.title}",
        reply_markup=_url_keyboard("Открыть задачу", url),
    )


async def _notify_reviewers(
    bot: Bot, settings: Settings, project: Project, user: User, document: str
) -> None:
    """Same notification bot/mobile users get from the in-bot submit flow
    (app/handlers/participant/projects_block5.py::project_submit_full) — the
    Mini App and Bot share one process, so this reuses the same Bot
    instance instead of a second, silent submission path."""
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    summary = (
        f"💡 Новый проект на рассмотрении\n\n{project.title}\n"
        f"Автор: {user.first_name} {user.last_name or ''} ({telegram})\n\n"
        "Полный файл проекта прикреплён ниже."
    )
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    keyboard = _url_keyboard(
        "Открыть модерацию",
        miniapp_admin_project_url(settings.effective_miniapp_url, project.id),
    )
    for chat_id in recipients:
        await safe_send(bot, chat_id, summary, reply_markup=keyboard)
        await safe_send_document(
            bot,
            chat_id,
            BufferedInputFile(
                BytesIO(document.encode("utf-8")).getvalue(),
                filename=f"ERA_project_{project.id}.txt",
            ),
            caption=f"Полный проект #{project.id}",
        )
