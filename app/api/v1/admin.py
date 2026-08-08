from __future__ import annotations

from datetime import datetime

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import Badge, Event, EventRegistration, Project, Task, TaskSubmission, User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.keyboards.participant import main_menu
from app.services import (
    event_moderation_service,
    event_registration_service,
    opportunity_service,
    project_workflow_service,
    task_review_service,
    user_management_service,
)
from app.services.admin_dashboard_service import dashboard_metrics, has_dashboard_access
from app.services.application_review_service import (
    approve_application,
    reject_application,
    request_more_info,
)
from app.services.authorization_service import (
    active_permissions,
    can_manage_events,
    can_manage_partners,
    can_manage_people,
    can_manage_permissions,
    can_manage_tasks,
    can_view_people,
    is_full_admin,
)
from app.services.chat_access_service import sync_user_chat_access
from app.services.notification_service import safe_send
from app.services.points_service import total_points
from app.services.project_workspace_service import can_review_projects
from app.utils import texts
from app.utils.constants import PERMISSIONS, PRIVILEGED_ROLES, ROLE_LABELS, ApplicationStatus
from app.utils.constants import Role as RoleEnum

router = APIRouter(prefix="/admin", tags=["admin"])

# Blunt defense against a stolen/leaked admin token being used to hammer
# decide-endpoints (approve/reject/moderate) — see
# docs/PRODUCTION_READINESS_AUDIT.md finding #11. Shared across all decide
# actions in this router (not per-endpoint) so rotating between them
# doesn't reset the budget. Generous enough that no real admin reviewing a
# queue by hand would ever hit it.
ADMIN_ACTION_RATE_LIMIT = 30
ADMIN_ACTION_RATE_LIMIT_WINDOW_SECONDS = 60


async def enforce_admin_action_rate_limit(request: Request) -> None:
    await enforce_rate_limit(
        request,
        key_prefix="admin_action",
        limit=ADMIN_ACTION_RATE_LIMIT,
        window_seconds=ADMIN_ACTION_RATE_LIMIT_WINDOW_SECONDS,
    )


async def require_dashboard_access(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class DashboardOut(BaseModel):
    metrics: dict[str, int]
    attention_total: int


@router.get("/dashboard", response_model=DashboardOut)
async def read_dashboard(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DashboardOut:
    metrics = await dashboard_metrics(session)
    return DashboardOut(metrics=metrics.values, attention_total=metrics.attention_total)


class ApplicationOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    city: str | None
    occupation: str | None
    motivation: str | None
    application_status: str
    created_at: str


def _to_application_out(user: User) -> ApplicationOut:
    return ApplicationOut(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        city=user.city,
        occupation=user.occupation,
        motivation=user.motivation,
        application_status=user.application_status,
        created_at=user.created_at.isoformat(),
    )


@router.get("/applications", response_model=list[ApplicationOut])
async def read_applications(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[ApplicationOut]:
    rows = await session.scalars(
        select(User)
        .where(
            User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]),
            User.is_archived.is_(False),
        )
        .order_by(User.created_at)
    )
    return [_to_application_out(u) for u in rows.all()]


class CommentIn(BaseModel):
    comment: str = ""


@router.post("/applications/{user_id}/approve", response_model=ApplicationOut)
async def approve_user_application(
    user_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ApplicationOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await approve_application(session, target, actor_id=admin.id)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        # Mirrors app/handlers/admin/panel.py::approve_user exactly, so a
        # Mini App approval looks identical to the Bot one to the user.
        await safe_send(
            bot,
            target.telegram_id,
            texts.APPLICATION_APPROVED,
            main_menu(settings.era_channel_url, miniapp_url=settings.effective_miniapp_url),
        )
        await safe_send(
            bot, target.telegram_id, "Перед стартом — короткие правила сообщества\n\n" + texts.CHAT_RULES
        )
        await sync_user_chat_access(bot, settings, session, target)
    return _to_application_out(target)


@router.post("/applications/{user_id}/reject", response_model=ApplicationOut)
async def reject_user_application(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ApplicationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await reject_application(session, target, actor_id=admin.id, comment=payload.comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        await safe_send(
            bot,
            target.telegram_id,
            f"{texts.APPLICATION_REJECTED}\n\nКомментарий: {payload.comment}",
        )
    return _to_application_out(target)


@router.post("/applications/{user_id}/request-info", response_model=ApplicationOut)
async def request_more_info_endpoint(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ApplicationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await request_more_info(session, target, actor_id=admin.id, comment=payload.comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        await safe_send(bot, target.telegram_id, texts.APPLICATION_NEEDS_INFO.format(comment=payload.comment))
    return _to_application_out(target)


class ProjectModerationOut(BaseModel):
    id: int
    title: str
    short_description: str
    status: str
    author_id: int
    submitted_at: str | None
    admin_comment: str | None


def _to_moderation_out(project: Project) -> ProjectModerationOut:
    return ProjectModerationOut(
        id=project.id,
        title=project.title,
        short_description=project.short_description,
        status=project.status,
        author_id=project.author_id,
        submitted_at=project.submitted_at.isoformat() if project.submitted_at else None,
        admin_comment=project.admin_comment,
    )


async def require_project_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not await can_review_projects(session, user, settings):
        raise HTTPException(status_code=403, detail="reviewer_access_required")
    return user


@router.get("/projects", response_model=list[ProjectModerationOut])
async def read_projects_for_review(
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectModerationOut]:
    projects = await project_workflow_service.list_projects_for_review(session)
    return [_to_moderation_out(project) for project in projects]


class ProjectDecisionIn(BaseModel):
    action: str
    comment: str


@router.post("/projects/{project_id}/decide", response_model=ProjectModerationOut)
async def decide_project_endpoint(
    project_id: int,
    payload: ProjectDecisionIn,
    reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> ProjectModerationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    if payload.action not in project_workflow_service.PROJECT_DECISION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    result = await project_workflow_service.decide_project(
        session, project, action=payload.action, comment=payload.comment, actor=reviewer
    )
    if bot is not None:
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"💡 {result.notice}\n\nПроект: {project.title}\n\nКомментарий команды ЭРА:\n{payload.comment}",
            )
    return _to_moderation_out(project)


# "Looking for a team" post moderation — approve/edit/reject/publish, the
# Mini App equivalent of app/handlers/admin/projects_block5_team.py.
# Distinct from ProjectWorkspace's in-app roles/applications (PR5): this
# broadcasts to the general Telegram chat, reaching people who aren't
# necessarily browsing the Mini App.


class TeamPostOut(BaseModel):
    project_id: int
    project_title: str
    author_name: str
    text: str
    status: str


async def _to_team_post_out(session: AsyncSession, project: Project) -> TeamPostOut:
    state = project_workflow_service.team_post_state(project)
    author = await session.get(User, project.author_id)
    return TeamPostOut(
        project_id=project.id,
        project_title=project.title,
        author_name=f"{author.first_name} {author.last_name or ''}".strip() if author else "—",
        text=state.text if state else "",
        status=state.status if state else "",
    )


@router.get("/projects/team-posts", response_model=list[TeamPostOut])
async def read_pending_team_posts(
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[TeamPostOut]:
    projects = await project_workflow_service.list_projects_with_pending_team_post(session)
    return [await _to_team_post_out(session, project) for project in projects]


@router.post("/projects/{project_id}/team-post/prepare", response_model=TeamPostOut)
async def prepare_team_post_endpoint(
    project_id: int,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.prepare_team_post(project):
        raise HTTPException(status_code=409, detail="no_team_post")
    return await _to_team_post_out(session, project)


class TeamPostEditIn(BaseModel):
    text: str


@router.post("/projects/{project_id}/team-post/edit", response_model=TeamPostOut)
async def edit_team_post_endpoint(
    project_id: int,
    payload: TeamPostEditIn,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    text = payload.text.strip()
    if len(text) < 30:
        raise HTTPException(status_code=422, detail="text_too_short")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.edit_team_post(project, text):
        raise HTTPException(status_code=409, detail="no_team_post")
    return await _to_team_post_out(session, project)


@router.post("/projects/{project_id}/team-post/reject", response_model=TeamPostOut)
async def reject_team_post_endpoint(
    project_id: int,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.reject_team_post(project):
        raise HTTPException(status_code=409, detail="no_team_post")
    if bot is not None:
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"Публикация для поиска команды по проекту «{project.title}» отклонена.",
            )
    return await _to_team_post_out(session, project)


@router.post("/projects/{project_id}/team-post/publish", response_model=TeamPostOut)
async def publish_team_post_endpoint(
    project_id: int,
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TeamPostOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    text = project_workflow_service.publish_team_post(project)
    if text is None:
        raise HTTPException(status_code=409, detail="not_prepared")
    if bot is not None:
        if settings.general_chat_id:
            await safe_send(bot, settings.general_chat_id, f"Команда для проекта ЭРА\n\n{project.title}\n\n{text}")
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"Публикация для поиска команды по проекту «{project.title}» одобрена.",
            )
    return await _to_team_post_out(session, project)


class EventModerationOut(BaseModel):
    id: int
    title: str
    description: str
    event_date: str
    event_time: str
    location: str
    status: str


def _to_event_moderation_out(event: Event) -> EventModerationOut:
    return EventModerationOut(
        id=event.id,
        title=event.title,
        description=event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(),
        location=event.location,
        status=event.status,
    )


async def require_event_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


@router.get("/events", response_model=list[EventModerationOut])
async def read_events_for_review(
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[EventModerationOut]:
    events = await event_moderation_service.list_events_for_review(session)
    return [_to_event_moderation_out(event) for event in events]


class EventDecisionIn(BaseModel):
    action: str
    comment: str = ""


@router.post("/events/{event_id}/decide", response_model=EventModerationOut)
async def decide_event_endpoint(
    event_id: int,
    payload: EventDecisionIn,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> EventModerationOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if payload.action not in event_moderation_service.EVENT_DECISION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await event_moderation_service.decide_event(
            session, event, action=payload.action, comment=payload.comment, actor=reviewer
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.owner is not None:
        await safe_send(bot, result.owner.telegram_id, result.notice)
    return _to_event_moderation_out(event)


# Post-moderation event operations — participants, attendance, points —
# the Mini App equivalent of
# app/handlers/admin/event_registration_block14.py. Distinct from the
# moderation queue above: these apply to events that are already
# approved/published, not ones still awaiting a decision.


class OperationalEventOut(BaseModel):
    id: int
    title: str
    event_date: str
    event_time: str
    location: str
    status: str
    points_for_visit: int
    registered: int
    free: int | str


@router.get("/events/operational", response_model=list[OperationalEventOut])
async def read_operational_events(
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[OperationalEventOut]:
    events = await event_registration_service.list_operational_events(session)
    result: list[OperationalEventOut] = []
    for event in events:
        stats = await event_registration_service.registration_stats(session, event)
        result.append(
            OperationalEventOut(
                id=event.id,
                title=event.title,
                event_date=event.event_date.isoformat(),
                event_time=event.event_time.isoformat(),
                location=event.location,
                status=event.status,
                points_for_visit=event.points_for_visit,
                registered=stats["registered"],
                free=stats["free"],
            )
        )
    return result


class EventParticipantOut(BaseModel):
    registration_id: int
    participant_id: int
    participant_name: str
    status: str


def _to_participant_out(registration: EventRegistration, participant: User) -> EventParticipantOut:
    return EventParticipantOut(
        registration_id=registration.id,
        participant_id=participant.id,
        participant_name=f"{participant.first_name} {participant.last_name or ''}".strip(),
        status=registration.status,
    )


@router.get("/events/{event_id}/participants", response_model=list[EventParticipantOut])
async def read_event_participants(
    event_id: int,
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[EventParticipantOut]:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    rows = await event_registration_service.list_participants(session, event_id)
    return [_to_participant_out(registration, participant) for registration, participant in rows]


class AttendanceIn(BaseModel):
    attended: bool


@router.post(
    "/events/{event_id}/registrations/{registration_id}/attendance",
    response_model=EventParticipantOut,
)
async def set_event_attendance_endpoint(
    event_id: int,
    registration_id: int,
    payload: AttendanceIn,
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> EventParticipantOut:
    registration = await session.get(EventRegistration, registration_id)
    if registration is None or registration.event_id != event_id:
        raise HTTPException(status_code=404, detail="registration_not_found")
    participant = await session.get(User, registration.user_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    event_registration_service.set_attendance(registration, payload.attended)
    return _to_participant_out(registration, participant)


class AttendanceAwardOut(BaseModel):
    awarded_count: int


@router.post("/events/{event_id}/award-attendance-points", response_model=AttendanceAwardOut)
async def award_event_attendance_points_endpoint(
    event_id: int,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> AttendanceAwardOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    newly_awarded = await event_registration_service.award_attendance_points(
        session, event, approved_by_id=reviewer.id
    )
    if bot is not None:
        for participant in newly_awarded:
            await safe_send(
                bot,
                participant.telegram_id,
                f"Участие в мероприятии «{event.title}» подтверждено.\n"
                f"Начислено: +{event.points_for_visit} баллов.",
            )
    return AttendanceAwardOut(awarded_count=len(newly_awarded))


class TaskSubmissionOut(BaseModel):
    id: int
    task_id: int
    task_title: str
    points: int
    participant_id: int
    participant_name: str
    text: str | None
    file_id: str | None
    status: str
    admin_comment: str | None


def _to_submission_out(
    submission: TaskSubmission, task: Task, participant: User
) -> TaskSubmissionOut:
    return TaskSubmissionOut(
        id=submission.id,
        task_id=task.id,
        task_title=task.title,
        points=task.points,
        participant_id=participant.id,
        participant_name=f"{participant.first_name} {participant.last_name or ''}".strip(),
        text=submission.text,
        file_id=submission.file_id,
        status=submission.status,
        admin_comment=submission.admin_comment,
    )


async def require_task_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_tasks(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="task_reviewer_access_required")
    return user


@router.get("/task-submissions", response_model=list[TaskSubmissionOut])
async def read_task_submissions(
    _reviewer: User = Depends(require_task_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[TaskSubmissionOut]:
    submissions = await task_review_service.list_pending_submissions(session)
    result: list[TaskSubmissionOut] = []
    for submission in submissions:
        task = await session.get(Task, submission.task_id)
        participant = await session.get(User, submission.user_id)
        if task is None or participant is None:
            continue
        result.append(_to_submission_out(submission, task, participant))
    return result


class TaskSubmissionDecisionIn(BaseModel):
    action: str
    comment: str = ""


@router.post("/task-submissions/{submission_id}/decide", response_model=TaskSubmissionOut)
async def decide_task_submission_endpoint(
    submission_id: int,
    payload: TaskSubmissionDecisionIn,
    reviewer: User = Depends(require_task_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> TaskSubmissionOut:
    submission = await session.get(TaskSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    task = await session.get(Task, submission.task_id)
    participant = await session.get(User, submission.user_id)
    if task is None or participant is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    if payload.action not in task_review_service.TASK_REVIEW_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await task_review_service.decide_submission(
            session,
            submission,
            task,
            participant,
            action=payload.action,
            comment=payload.comment,
            actor=reviewer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.participant_notice:
        await safe_send(bot, participant.telegram_id, result.participant_notice)
    return _to_submission_out(submission, task, participant)


class OfferApplicationOut(BaseModel):
    id: int
    offer_id: int
    offer_title: str
    point_cost: int
    participant_id: int
    participant_name: str
    participant_balance: int
    status: str


def _to_offer_application_out(
    application: PartnerOfferApplication,
    offer: PartnerInitiative,
    participant: User,
    balance: int,
) -> OfferApplicationOut:
    return OfferApplicationOut(
        id=application.id,
        offer_id=offer.id,
        offer_title=offer.title,
        point_cost=offer.point_cost,
        participant_id=participant.id,
        participant_name=f"{participant.first_name} {participant.last_name or ''}".strip(),
        participant_balance=balance,
        status=application.status,
    )


async def require_offer_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_partners(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="offer_reviewer_access_required")
    return user


@router.get("/offer-applications", response_model=list[OfferApplicationOut])
async def read_offer_applications(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[OfferApplicationOut]:
    applications = await opportunity_service.list_pending_offer_applications(session)
    result: list[OfferApplicationOut] = []
    for application in applications:
        offer = await session.get(PartnerInitiative, application.initiative_id)
        participant = await session.get(User, application.user_id)
        if offer is None or participant is None:
            continue
        balance = await total_points(session, participant.id)
        result.append(_to_offer_application_out(application, offer, participant, balance))
    return result


class OfferApplicationDecisionIn(BaseModel):
    action: str


@router.post("/offer-applications/{application_id}/decide", response_model=OfferApplicationOut)
async def decide_offer_application_endpoint(
    application_id: int,
    payload: OfferApplicationDecisionIn,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferApplicationOut:
    application = await session.get(PartnerOfferApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    offer = await session.get(PartnerInitiative, application.initiative_id)
    participant = await session.get(User, application.user_id)
    if offer is None or participant is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    if payload.action not in opportunity_service.OFFER_APPLICATION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await opportunity_service.decide_offer_application(
            session, application, offer, participant, action=payload.action, actor=reviewer
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.participant_notice:
        await safe_send(bot, participant.telegram_id, result.participant_notice)
    balance = await total_points(session, participant.id)
    return _to_offer_application_out(application, offer, participant, balance)


# ---------------------------------------------------------------------------
# Partners + offer catalog management — the Mini App equivalent of
# app/handlers/admin/partners_admin.py and the create/list/toggle/archive
# half of app/handlers/admin/partner_offers_block16.py. The application
# review above only ever covered reviewing participants' applications to
# offers that already existed — there was no way to actually create or
# manage a partner or an offer itself from the Mini App.
# ---------------------------------------------------------------------------


class PartnerOut(BaseModel):
    id: int
    name: str
    description: str
    source_url: str | None
    is_active: bool
    is_archived: bool


def _to_partner_out(partner: Partner) -> PartnerOut:
    return PartnerOut(
        id=partner.id,
        name=partner.name,
        description=partner.description,
        source_url=partner.source_url,
        is_active=partner.is_active,
        is_archived=partner.is_archived,
    )


@router.get("/partners", response_model=list[PartnerOut])
async def list_partners_endpoint(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[PartnerOut]:
    partners = await opportunity_service.list_partners(session)
    return [_to_partner_out(partner) for partner in partners]


class PartnerCreateIn(BaseModel):
    name: str
    description: str
    source_url: str = ""


@router.post("/partners", response_model=PartnerOut)
async def create_partner_endpoint(
    payload: PartnerCreateIn,
    reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PartnerOut:
    name = payload.name.strip()
    description = payload.description.strip()
    if not name or not description:
        raise HTTPException(status_code=422, detail="name_and_description_required")
    partner = await opportunity_service.create_partner(
        session,
        name=name[:255],
        description=description,
        source_url=payload.source_url.strip()[:500] or None,
        created_by_id=reviewer.id,
    )
    return _to_partner_out(partner)


class PartnerActiveIn(BaseModel):
    active: bool


@router.post("/partners/{partner_id}/active", response_model=PartnerOut)
async def set_partner_active_endpoint(
    partner_id: int,
    payload: PartnerActiveIn,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PartnerOut:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="partner_not_found")
    opportunity_service.set_partner_active(partner, payload.active)
    return _to_partner_out(partner)


@router.post("/partners/{partner_id}/archive", response_model=PartnerOut)
async def archive_partner_endpoint(
    partner_id: int,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PartnerOut:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="partner_not_found")
    opportunity_service.archive_partner(partner)
    return _to_partner_out(partner)


class OfferAdminOut(BaseModel):
    id: int
    partner_id: int
    partner_name: str
    title: str
    description: str
    point_cost: int
    quantity: int | None
    expires_at: str | None
    instruction: str | None
    source_url: str | None
    is_active: bool
    is_archived: bool


def _to_offer_admin_out(offer: PartnerInitiative, partner: Partner) -> OfferAdminOut:
    return OfferAdminOut(
        id=offer.id,
        partner_id=partner.id,
        partner_name=partner.name,
        title=offer.title,
        description=offer.description,
        point_cost=offer.point_cost,
        quantity=offer.quantity,
        expires_at=offer.expires_at.isoformat() if offer.expires_at else None,
        instruction=offer.instruction,
        source_url=offer.source_url,
        is_active=offer.is_active,
        is_archived=offer.is_archived,
    )


@router.get("/offers", response_model=list[OfferAdminOut])
async def list_offers_endpoint(
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[OfferAdminOut]:
    rows = await opportunity_service.list_offers_admin(session)
    return [_to_offer_admin_out(offer, partner) for offer, partner in rows]


class OfferCreateIn(BaseModel):
    partner_id: int
    title: str
    description: str
    point_cost: int
    quantity: int | None = None
    expires_at: str | None = None
    instruction: str = ""
    source_url: str = ""


@router.post("/offers", response_model=OfferAdminOut)
async def create_offer_endpoint(
    payload: OfferCreateIn,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferAdminOut:
    title = payload.title.strip()
    description = payload.description.strip()
    if not title or not description:
        raise HTTPException(status_code=422, detail="title_and_description_required")
    if payload.point_cost < 0:
        raise HTTPException(status_code=422, detail="invalid_point_cost")
    if payload.quantity is not None and payload.quantity < 1:
        raise HTTPException(status_code=422, detail="invalid_quantity")
    partner = await session.get(Partner, payload.partner_id)
    if partner is None or partner.is_archived:
        raise HTTPException(status_code=404, detail="partner_not_found")
    expires_at = None
    if payload.expires_at:
        try:
            expires_at = datetime.strptime(payload.expires_at, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_expires_at") from None
    offer = await opportunity_service.create_offer(
        session,
        partner_id=partner.id,
        title=title[:255],
        description=description[:3000],
        point_cost=payload.point_cost,
        quantity=payload.quantity,
        expires_at=expires_at,
        instruction=payload.instruction.strip()[:3000] or None,
        source_url=payload.source_url.strip()[:500] or None,
    )
    return _to_offer_admin_out(offer, partner)


class OfferActiveIn(BaseModel):
    active: bool


@router.post("/offers/{offer_id}/active", response_model=OfferAdminOut)
async def set_offer_active_endpoint(
    offer_id: int,
    payload: OfferActiveIn,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferAdminOut:
    row = await opportunity_service.get_offer_with_partner(session, offer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="offer_not_found")
    offer, partner = row
    opportunity_service.set_offer_active(offer, payload.active)
    return _to_offer_admin_out(offer, partner)


@router.post("/offers/{offer_id}/archive", response_model=OfferAdminOut)
async def archive_offer_endpoint(
    offer_id: int,
    _reviewer: User = Depends(require_offer_reviewer),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> OfferAdminOut:
    row = await opportunity_service.get_offer_with_partner(session, offer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="offer_not_found")
    offer, partner = row
    opportunity_service.archive_offer(offer)
    return _to_offer_admin_out(offer, partner)


# ---------------------------------------------------------------------------
# People — user directory + profile actions. The Mini App equivalent of the
# bot's admin:participants list and admin:user:* card
# (app/handlers/admin/rights_block6.py, user_profile_block3_safe.py) — this
# was the single biggest admin capability that had no Mini App equivalent at
# all (search/list every user, not just pending applications; change role;
# block/unblock; archive/unarchive; grant technical permissions; award
# points or a badge directly).
# ---------------------------------------------------------------------------


async def require_people_viewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_view_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_view_access_required")
    return user


async def require_people_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_manage_access_required")
    return user


async def require_permissions_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_permissions(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="permissions_manage_access_required")
    return user


async def require_points_awarder(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    # Mirrors user_profile_block3_safe.py::is_admin for points/badge actions:
    # full admins always can; everyone else needs the dedicated
    # points.award grant specifically — not people.manage, which is a
    # separate, narrower grant on purpose (editing someone's role/status
    # shouldn't automatically also let you move points).
    if is_full_admin(user, settings, user.telegram_id) or "points.award" in active_permissions(user):
        return user
    raise HTTPException(status_code=403, detail="points_award_access_required")


class UserListItemOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    role: str
    application_status: str
    is_blocked: bool
    is_archived: bool


class UserListOut(BaseModel):
    items: list[UserListItemOut]
    total: int


@router.get("/users", response_model=UserListOut)
async def list_users_endpoint(
    query: str = "",
    role: str | None = None,
    include_archived: bool = False,
    limit: int = 30,
    offset: int = 0,
    _viewer: User = Depends(require_people_viewer),
    session: AsyncSession = Depends(get_session),
) -> UserListOut:
    rows, total = await user_management_service.search_users(
        session,
        query=query,
        role=role,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return UserListOut(
        items=[
            UserListItemOut(
                id=u.id,
                telegram_id=u.telegram_id,
                first_name=u.first_name,
                last_name=u.last_name,
                username=u.username,
                role=u.role,
                application_status=u.application_status,
                is_blocked=u.is_blocked,
                is_archived=u.is_archived,
            )
            for u in rows
        ],
        total=total,
    )


class BadgeOut(BaseModel):
    id: int
    name: str


class SocialLinkOut(BaseModel):
    platform: str
    url: str


class UserDetailOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    role: str
    application_status: str
    participation_status: str
    is_blocked: bool
    is_archived: bool
    city: str | None
    phone: str | None
    email: str | None
    occupation: str | None
    motivation: str | None
    points_balance: int
    portfolio_count: int
    badges: list[BadgeOut]
    available_badges: list[BadgeOut]
    permissions: dict[str, bool]
    social_links: list[SocialLinkOut]
    can_manage: bool
    can_manage_permissions: bool
    can_award_points: bool


async def _build_user_detail_out(
    session: AsyncSession, target: User, viewer: User, settings: Settings
) -> UserDetailOut:
    balance = await total_points(session, target.id)
    owned = await user_management_service.user_badges(session, target.id)
    available = await user_management_service.available_badges(session, target.id)
    links = await user_management_service.social_links(session, target.id)
    active = user_management_service.active_permission_set(target)
    return UserDetailOut(
        id=target.id,
        telegram_id=target.telegram_id,
        first_name=target.first_name,
        last_name=target.last_name,
        username=target.username,
        role=target.role,
        application_status=target.application_status,
        participation_status=target.participation_status,
        is_blocked=target.is_blocked,
        is_archived=target.is_archived,
        city=target.city,
        phone=target.phone,
        email=target.email,
        occupation=target.occupation,
        motivation=target.motivation,
        points_balance=balance,
        portfolio_count=await user_management_service.portfolio_count(session, target.id),
        badges=[BadgeOut(id=b.id, name=b.name) for b in owned],
        available_badges=[BadgeOut(id=b.id, name=b.name) for b in available],
        permissions={permission: permission in active for permission in PERMISSIONS},
        social_links=[SocialLinkOut(platform=link.platform, url=link.url) for link in links],
        can_manage=can_manage_people(viewer, settings, viewer.telegram_id),
        can_manage_permissions=can_manage_permissions(viewer, settings, viewer.telegram_id),
        can_award_points=is_full_admin(viewer, settings, viewer.telegram_id)
        or "points.award" in active_permissions(viewer),
    )


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def read_user_detail(
    user_id: int,
    viewer: User = Depends(require_people_viewer),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return await _build_user_detail_out(session, target, viewer, settings)


class RoleChangeIn(BaseModel):
    role: str


@router.post("/users/{user_id}/role", response_model=UserDetailOut)
async def change_user_role(
    user_id: int,
    payload: RoleChangeIn,
    manager: User = Depends(require_people_manager),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    try:
        new_role = RoleEnum(payload.role)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_role") from None
    decision = await user_management_service.change_role(
        session,
        actor=manager,
        actor_telegram_id=manager.telegram_id,
        target=target,
        new_role=new_role,
        settings=settings,
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_role")
    if bot is not None:
        await sync_user_chat_access(bot, settings, session, target)
        await safe_send(
            bot,
            target.telegram_id,
            f"Ваша роль в ЭРА обновлена: {ROLE_LABELS.get(new_role, new_role.value)}\n\n"
            "Новые возможности уже доступны в меню",
            main_menu(
                settings.era_channel_url,
                privileged=new_role in PRIVILEGED_ROLES,
                admin=new_role == RoleEnum.ADMIN,
                miniapp_url=settings.effective_miniapp_url,
            ),
        )
    return await _build_user_detail_out(session, target, manager, settings)


class BlockIn(BaseModel):
    blocked: bool


@router.post("/users/{user_id}/block", response_model=UserDetailOut)
async def set_user_blocked(
    user_id: int,
    payload: BlockIn,
    manager: User = Depends(require_people_manager),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    decision = await user_management_service.set_blocked(
        session, actor=manager, target=target, settings=settings, blocked=payload.blocked
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_access")
    if bot is not None:
        await sync_user_chat_access(bot, settings, session, target)
    return await _build_user_detail_out(session, target, manager, settings)


class ArchiveIn(BaseModel):
    archived: bool


@router.post("/users/{user_id}/archive", response_model=UserDetailOut)
async def set_user_archived(
    user_id: int,
    payload: ArchiveIn,
    manager: User = Depends(require_people_manager),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> UserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    decision = await user_management_service.set_archived(
        session, actor=manager, target=target, settings=settings, archived=payload.archived
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_access")
    if bot is not None:
        await sync_user_chat_access(bot, settings, session, target)
    return await _build_user_detail_out(session, target, manager, settings)


class PermissionToggleOut(BaseModel):
    permission: str
    enabled: bool


@router.post("/users/{user_id}/permissions/{permission}", response_model=PermissionToggleOut)
async def toggle_user_permission(
    user_id: int,
    permission: str,
    manager: User = Depends(require_permissions_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PermissionToggleOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    decision, enabled = await user_management_service.toggle_permission(
        session, actor=manager, target=target, permission=permission
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail=decision.reason or "cannot_change_permission")
    return PermissionToggleOut(permission=permission, enabled=enabled)


class PointsAwardIn(BaseModel):
    amount: int
    reason: str


class PointsAwardOut(BaseModel):
    balance: int


@router.post("/users/{user_id}/points", response_model=PointsAwardOut)
async def award_user_points(
    user_id: int,
    payload: PointsAwardIn,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> PointsAwardOut:
    reason = payload.reason.strip()
    if payload.amount == 0 or abs(payload.amount) > user_management_service.MAX_POINTS_ADJUSTMENT:
        raise HTTPException(status_code=422, detail="invalid_amount")
    if not reason:
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    balance = await user_management_service.award_points(
        session, target=target, amount=payload.amount, reason=reason, approved_by_id=awarder.id
    )
    if bot is not None:
        await safe_send(
            bot,
            target.telegram_id,
            f"Ваш баланс изменён на {payload.amount:+d} баллов\nПричина: {reason}\n\n"
            f"Текущий баланс: {balance} баллов",
        )
    return PointsAwardOut(balance=balance)


class BadgeAwardIn(BaseModel):
    reason: str


@router.post("/users/{user_id}/badges/{badge_id}", response_model=BadgeOut)
async def award_user_badge(
    user_id: int,
    badge_id: int,
    payload: BadgeAwardIn,
    awarder: User = Depends(require_points_awarder),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> BadgeOut:
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    badge = await session.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(status_code=404, detail="badge_not_found")
    awarded = await user_management_service.award_badge(
        session, target=target, badge=badge, reason=reason, awarded_by_id=awarder.id
    )
    if not awarded:
        raise HTTPException(status_code=409, detail="already_awarded")
    if bot is not None:
        await safe_send(bot, target.telegram_id, f"Вы получили знак «{badge.name}» 🌟\n\n{reason}")
    return BadgeOut(id=badge.id, name=badge.name)
