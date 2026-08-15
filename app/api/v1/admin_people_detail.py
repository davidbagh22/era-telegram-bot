from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.management_models import AdminSurvey, AdminSurveyResponse
from app.database.models import (
    Badge,
    Event,
    EventActivity,
    EventActivitySubmission,
    EventRegistration,
    Feedback,
    PointTransaction,
    PortfolioItem,
    Project,
    ProjectMember,
    Task,
    TaskSubmission,
    User,
    UserBadge,
)
from app.database.socials import SocialProfile
from app.services.authorization_service import (
    active_permissions,
    can_manage_people,
    can_manage_permissions,
    can_view_people,
    is_full_admin,
)
from app.services.points_service import total_points
from app.services import user_management_service
from app.utils.constants import PERMISSIONS, RegistrationStatus

router = APIRouter(prefix="/admin", tags=["admin"])


class BadgeDetailOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    reason: str | None = None
    awarded_at: str | None = None


class SocialLinkOut(BaseModel):
    platform: str
    url: str


class ActivityRecordOut(BaseModel):
    id: int
    title: str
    subtitle: str | None = None
    status: str | None = None
    date: str | None = None
    points: int | None = None


class SurveyAnswerOut(BaseModel):
    question: str
    answer: str


class SurveyRecordOut(BaseModel):
    id: int
    title: str
    submitted_at: str | None
    answers: list[SurveyAnswerOut]


class ParticipantMetricsOut(BaseModel):
    events_registered: int
    events_attended: int
    no_shows: int
    tasks_submitted: int
    tasks_approved: int
    projects_authored: int
    project_memberships: int
    confirmed_project_contributions: int
    surveys_completed: int
    activity_submissions_approved: int
    events_responsible: int
    points_transactions: int


class LeadershipSignalsOut(BaseModel):
    summary: str
    strengths: list[str]
    growth_areas: list[str]


class PointSuggestionOut(BaseModel):
    amount: int
    reason: str
    evidence: list[str]


class BadgeSuggestionOut(BaseModel):
    badge_id: int
    badge_name: str
    reason: str
    evidence: list[str]


class ParticipantActivityOut(BaseModel):
    events: list[ActivityRecordOut]
    tasks: list[ActivityRecordOut]
    projects: list[ActivityRecordOut]
    point_history: list[ActivityRecordOut]
    portfolio: list[ActivityRecordOut]


class RichUserDetailOut(BaseModel):
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
    birth_date: str | None
    age: int | None
    city: str | None
    phone: str | None
    email: str | None
    education_work: str | None
    occupation: str | None
    skills: list[str]
    experience: str | None
    motivation: str | None
    available_time: str | None
    desired_path: str | None
    departments: list[str]
    directions: list[str]
    created_at: str
    photo_attached: bool
    photo_data_url: str | None
    points_balance: int
    portfolio_count: int
    badges: list[BadgeDetailOut]
    available_badges: list[BadgeDetailOut]
    permissions: dict[str, bool]
    social_links: list[SocialLinkOut]
    can_manage: bool
    can_manage_permissions: bool
    can_award_points: bool
    metrics: ParticipantMetricsOut
    leadership: LeadershipSignalsOut
    points_suggestion: PointSuggestionOut | None
    badge_suggestions: list[BadgeSuggestionOut]
    activity: ParticipantActivityOut
    surveys: list[SurveyRecordOut]


async def require_people_viewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_view_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_view_access_required")
    return user


async def _photo_data_url(bot: Bot | None, profile: SocialProfile | None) -> str | None:
    if bot is None or profile is None or not profile.photo_file_id:
        return None
    try:
        downloaded = await bot.download(profile.photo_file_id)
        if downloaded is None:
            return None
        raw = downloaded.getvalue() if hasattr(downloaded, "getvalue") else downloaded.read()
        if not raw:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        # A Telegram media lookup must never make the whole participant card unusable.
        return None


def _date_iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _signal_text(metrics: ParticipantMetricsOut) -> LeadershipSignalsOut:
    strengths: list[str] = []
    growth: list[str] = []

    if metrics.events_attended >= 3:
        strengths.append(f"Регулярно участвует офлайн/онлайн: {metrics.events_attended} подтверждённых посещений.")
    if metrics.tasks_approved >= 2:
        strengths.append(f"Доводит задачи до результата: {metrics.tasks_approved} принятых работ.")
    if metrics.projects_authored >= 1:
        strengths.append(f"Проявляет инициативу: {metrics.projects_authored} собственных проектов в системе.")
    if metrics.confirmed_project_contributions >= 1:
        strengths.append(
            f"Есть подтверждённый вклад в командные проекты: {metrics.confirmed_project_contributions}."
        )
    if metrics.surveys_completed >= 2:
        strengths.append(f"Даёт обратную связь: заполнено {metrics.surveys_completed} опросов.")
    if metrics.activity_submissions_approved >= 2:
        strengths.append(
            f"Активен после мероприятий: принято {metrics.activity_submissions_approved} дополнительных активностей."
        )

    if metrics.events_attended == 0:
        growth.append("Пока нет подтверждённых посещений — стоит вовлечь в ближайшее подходящее событие.")
    if metrics.tasks_approved == 0:
        growth.append("Нет принятых заданий — можно дать небольшую конкретную задачу и посмотреть на темп работы.")
    if metrics.projects_authored == 0 and metrics.project_memberships == 0:
        growth.append("Пока нет проектной практики — логичный следующий шаг: роль в команде действующего проекта.")
    if metrics.surveys_completed == 0:
        growth.append("Нет ответов на опросы — интересы и ожидания лучше уточнить напрямую.")

    if not strengths:
        summary = "Данных пока мало: профиль лучше оценивать по анкете и первым действиям, без ранних выводов."
    elif len(strengths) >= 3:
        summary = "Высокая подтверждённая вовлечённость по нескольким направлениям."
    else:
        summary = "Есть подтверждённые сильные сигналы; следующий шаг — расширять ответственность постепенно."

    return LeadershipSignalsOut(summary=summary, strengths=strengths, growth_areas=growth)


def _recognition_suggestions(
    metrics: ParticipantMetricsOut,
    available_badges: list[Badge],
    *,
    recent_score: int,
    has_recent_manual_bonus: bool,
    directions: list[str],
) -> tuple[PointSuggestionOut | None, list[BadgeSuggestionOut]]:
    evidence: list[str] = []
    if metrics.events_attended:
        evidence.append(f"{metrics.events_attended} посещений")
    if metrics.tasks_approved:
        evidence.append(f"{metrics.tasks_approved} принятых задач")
    if metrics.projects_authored:
        evidence.append(f"{metrics.projects_authored} собственных проектов")
    if metrics.confirmed_project_contributions:
        evidence.append(f"{metrics.confirmed_project_contributions} подтверждённых вкладов в проекты")
    if metrics.surveys_completed:
        evidence.append(f"{metrics.surveys_completed} опросов")

    point_suggestion: PointSuggestionOut | None = None
    if recent_score >= 3 and not has_recent_manual_bonus:
        amount = 20 if recent_score >= 7 else 10
        point_suggestion = PointSuggestionOut(
            amount=amount,
            reason="Дополнительный бонус за стабильную активность в ЭРА",
            evidence=evidence[:4],
        )

    by_name = {badge.name: badge for badge in available_badges}
    suggestions: list[BadgeSuggestionOut] = []

    def add(name: str, reason: str, proof: list[str]) -> None:
        badge = by_name.get(name)
        if badge and len(suggestions) < 4:
            suggestions.append(
                BadgeSuggestionOut(
                    badge_id=badge.id,
                    badge_name=badge.name,
                    reason=reason,
                    evidence=proof,
                )
            )

    total_actions = (
        metrics.events_attended
        + metrics.tasks_approved
        + metrics.projects_authored
        + metrics.confirmed_project_contributions
        + metrics.activity_submissions_approved
    )
    if total_actions >= 1:
        add("Первый шаг", "За первое подтверждённое действие в ЭРА", evidence[:2] or ["Есть подтверждённая активность"])
    if metrics.surveys_completed >= 2:
        add("Голос ЭРА", "За регулярную содержательную обратную связь", [f"Заполнено опросов: {metrics.surveys_completed}"])
    if metrics.events_attended >= 3 or metrics.tasks_approved >= 3:
        add("Надёжный участник", "За стабильность и доведение участия до результата", evidence[:3])
    if metrics.project_memberships >= 1 or metrics.confirmed_project_contributions >= 1:
        add("Командный игрок", "За подтверждённую работу в проектной команде", [f"Участие в проектах: {metrics.project_memberships}", f"Подтверждённый вклад: {metrics.confirmed_project_contributions}"])
    if metrics.events_responsible >= 1:
        add("Организатор", "За ответственность за проведение мероприятий", [f"Мероприятий в ответственности: {metrics.events_responsible}"])
    if metrics.projects_authored >= 1:
        add("Проектный автор", "За запуск собственной проектной инициативы", [f"Создано проектов: {metrics.projects_authored}"])
    if "Медиа" in directions and metrics.tasks_approved >= 1:
        add("Медиа-двигатель", "За подтверждённую активность при интересе к медиа-направлению", ["Выбрано направление «Медиа»", f"Принятых задач: {metrics.tasks_approved}"])
    if recent_score >= 8:
        add("Прорыв месяца", "За заметный рост активности за последние 90 дней", [f"Индекс недавней активности: {recent_score}"])

    return point_suggestion, suggestions


@router.get("/users/{user_id}", response_model=RichUserDetailOut)
async def read_rich_user_detail(
    user_id: int,
    viewer: User = Depends(require_people_viewer),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> RichUserDetailOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    profile = await session.scalar(select(SocialProfile).where(SocialProfile.user_id == user_id))
    photo_data_url = await _photo_data_url(bot, profile)
    social_links = await user_management_service.social_links(session, user_id)
    available_badges = await user_management_service.available_badges(session, user_id)

    badge_rows = (
        await session.execute(
            select(UserBadge, Badge)
            .join(Badge, Badge.id == UserBadge.badge_id)
            .where(UserBadge.user_id == user_id)
            .order_by(UserBadge.created_at.desc())
        )
    ).all()

    event_rows = (
        await session.execute(
            select(EventRegistration, Event)
            .join(Event, Event.id == EventRegistration.event_id)
            .where(EventRegistration.user_id == user_id)
            .order_by(Event.event_date.desc(), Event.event_time.desc())
        )
    ).all()
    task_rows = (
        await session.execute(
            select(TaskSubmission, Task)
            .join(Task, Task.id == TaskSubmission.task_id)
            .where(TaskSubmission.user_id == user_id)
            .order_by(TaskSubmission.created_at.desc())
        )
    ).all()
    authored_projects = list(
        (
            await session.scalars(
                select(Project).where(Project.author_id == user_id).order_by(Project.created_at.desc())
            )
        ).all()
    )
    membership_rows = (
        await session.execute(
            select(ProjectMember, Project)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user_id)
            .order_by(ProjectMember.created_at.desc())
        )
    ).all()
    activity_rows = (
        await session.execute(
            select(EventActivitySubmission, EventActivity, Event)
            .join(EventActivity, EventActivity.id == EventActivitySubmission.activity_id)
            .join(Event, Event.id == EventActivity.event_id)
            .where(EventActivitySubmission.user_id == user_id)
            .order_by(EventActivitySubmission.created_at.desc())
        )
    ).all()
    survey_rows = (
        await session.execute(
            select(AdminSurveyResponse, AdminSurvey)
            .join(AdminSurvey, AdminSurvey.id == AdminSurveyResponse.survey_id)
            .where(AdminSurveyResponse.user_id == user_id)
            .order_by(AdminSurveyResponse.submitted_at.desc().nullslast(), AdminSurveyResponse.created_at.desc())
        )
    ).all()
    point_rows = list(
        (
            await session.scalars(
                select(PointTransaction)
                .where(PointTransaction.user_id == user_id)
                .order_by(PointTransaction.created_at.desc())
                .limit(20)
            )
        ).all()
    )
    portfolio_rows = list(
        (
            await session.scalars(
                select(PortfolioItem)
                .where(PortfolioItem.user_id == user_id)
                .order_by(PortfolioItem.created_at.desc())
                .limit(12)
            )
        ).all()
    )
    feedback_rows = (
        await session.execute(
            select(Feedback, Event)
            .join(Event, Event.id == Feedback.event_id)
            .where(Feedback.user_id == user_id)
            .order_by(Feedback.created_at.desc())
        )
    ).all()

    attended = sum(1 for registration, _ in event_rows if registration.status == RegistrationStatus.ATTENDED)
    no_shows = sum(1 for registration, _ in event_rows if registration.status == RegistrationStatus.NO_SHOW)
    tasks_approved = sum(1 for submission, _ in task_rows if submission.status == "approved")
    approved_activities = sum(1 for submission, _, _ in activity_rows if submission.status == "approved")
    confirmed_contributions = sum(
        1 for member, _ in membership_rows if member.contribution_status == "confirmed"
    )
    events_responsible = int(
        await session.scalar(select(func.count()).select_from(Event).where(Event.responsible_id == user_id)) or 0
    )
    points_transactions = int(
        await session.scalar(
            select(func.count()).select_from(PointTransaction).where(PointTransaction.user_id == user_id)
        )
        or 0
    )

    metrics = ParticipantMetricsOut(
        events_registered=len(event_rows),
        events_attended=attended,
        no_shows=no_shows,
        tasks_submitted=len(task_rows),
        tasks_approved=tasks_approved,
        projects_authored=len(authored_projects),
        project_memberships=len(membership_rows),
        confirmed_project_contributions=confirmed_contributions,
        surveys_completed=len(survey_rows),
        activity_submissions_approved=approved_activities,
        events_responsible=events_responsible,
        points_transactions=points_transactions,
    )

    cutoff_date = date.today() - timedelta(days=90)
    recent_attended = sum(
        1
        for registration, event in event_rows
        if registration.status == RegistrationStatus.ATTENDED and event.event_date >= cutoff_date
    )
    recent_tasks = sum(
        1
        for submission, _ in task_rows
        if submission.status == "approved" and submission.created_at.date() >= cutoff_date
    )
    recent_projects = sum(
        1 for project in authored_projects if project.created_at.date() >= cutoff_date
    )
    recent_surveys = sum(
        1
        for response, _ in survey_rows
        if (response.submitted_at or response.created_at).date() >= cutoff_date
    )
    recent_score = recent_attended + recent_tasks * 2 + recent_projects * 2 + recent_surveys
    recent_manual_bonus = bool(
        await session.scalar(
            select(func.count())
            .select_from(PointTransaction)
            .where(
                PointTransaction.user_id == user_id,
                PointTransaction.source_type == "manual_points",
                PointTransaction.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
        )
    )

    departments = [
        link.department.name
        for link in (target.departments or [])
        if getattr(link, "department", None) is not None
    ]
    directions = [
        link.direction.name
        for link in (target.directions or [])
        if getattr(link, "direction", None) is not None
    ]
    point_suggestion, badge_suggestions = _recognition_suggestions(
        metrics,
        available_badges,
        recent_score=recent_score,
        has_recent_manual_bonus=recent_manual_bonus,
        directions=directions,
    )

    project_records: list[ActivityRecordOut] = []
    project_records.extend(
        ActivityRecordOut(
            id=project.id,
            title=project.title,
            subtitle="Автор проекта",
            status=project.status,
            date=_date_iso(project.created_at),
        )
        for project in authored_projects[:10]
    )
    project_records.extend(
        ActivityRecordOut(
            id=project.id,
            title=project.title,
            subtitle=(member.contribution_role_title or "Участник команды")
            + (" · вклад подтверждён" if member.contribution_status == "confirmed" else ""),
            status=member.status,
            date=_date_iso(member.joined_at or member.created_at),
        )
        for member, project in membership_rows[:10]
    )
    project_records.sort(key=lambda item: item.date or "", reverse=True)

    surveys = [
        SurveyRecordOut(
            id=survey.id,
            title=survey.title,
            submitted_at=_date_iso(response.submitted_at or response.created_at),
            answers=[
                SurveyAnswerOut(
                    question=str(answer.get("question") or answer.get("label") or "Вопрос"),
                    answer=str(answer.get("answer") or answer.get("value") or "—"),
                )
                for answer in (response.answers_json or [])
            ],
        )
        for response, survey in survey_rows
    ]

    # Event feedback is useful leadership context, so append it to the event subtitle
    # instead of hiding it in a separate technical table.
    feedback_by_event = {
        event.id: feedback for feedback, event in feedback_rows
    }
    event_records: list[ActivityRecordOut] = []
    for registration, event in event_rows[:15]:
        feedback = feedback_by_event.get(event.id)
        subtitle = event.location
        if feedback is not None:
            subtitle = f"{subtitle} · оценка {feedback.rating}/5"
        event_records.append(
            ActivityRecordOut(
                id=event.id,
                title=event.title,
                subtitle=subtitle,
                status=registration.status,
                date=event.event_date.isoformat(),
            )
        )

    active = user_management_service.active_permission_set(target)
    return RichUserDetailOut(
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
        birth_date=target.birth_date.isoformat() if target.birth_date else None,
        age=target.age,
        city=target.city,
        phone=target.phone,
        email=target.email,
        education_work=target.education_work,
        occupation=target.occupation,
        skills=list(target.skills or []),
        experience=target.experience,
        motivation=target.motivation,
        available_time=target.available_time,
        desired_path=target.desired_path,
        departments=departments,
        directions=directions,
        created_at=target.created_at.isoformat(),
        photo_attached=bool(profile and profile.photo_file_id),
        photo_data_url=photo_data_url,
        points_balance=await total_points(session, user_id),
        portfolio_count=len(portfolio_rows),
        badges=[
            BadgeDetailOut(
                id=badge.id,
                name=badge.name,
                description=badge.description,
                reason=user_badge.reason,
                awarded_at=user_badge.created_at.isoformat(),
            )
            for user_badge, badge in badge_rows
        ],
        available_badges=[
            BadgeDetailOut(id=badge.id, name=badge.name, description=badge.description)
            for badge in available_badges
        ],
        permissions={permission: permission in active for permission in PERMISSIONS},
        social_links=[SocialLinkOut(platform=link.platform, url=link.url) for link in social_links],
        can_manage=can_manage_people(viewer, settings, viewer.telegram_id),
        can_manage_permissions=can_manage_permissions(viewer, settings, viewer.telegram_id),
        can_award_points=is_full_admin(viewer, settings, viewer.telegram_id)
        or "points.award" in active_permissions(viewer),
        metrics=metrics,
        leadership=_signal_text(metrics),
        points_suggestion=point_suggestion,
        badge_suggestions=badge_suggestions,
        activity=ParticipantActivityOut(
            events=event_records,
            tasks=[
                ActivityRecordOut(
                    id=task.id,
                    title=task.title,
                    subtitle=submission.admin_comment,
                    status=submission.status,
                    date=_date_iso(submission.created_at),
                    points=task.points,
                )
                for submission, task in task_rows[:15]
            ],
            projects=project_records[:15],
            point_history=[
                ActivityRecordOut(
                    id=row.id,
                    title=row.reason,
                    subtitle=row.source_type,
                    status=None,
                    date=_date_iso(row.created_at),
                    points=row.points,
                )
                for row in point_rows
            ],
            portfolio=[
                ActivityRecordOut(
                    id=row.id,
                    title=row.title,
                    subtitle=row.description,
                    status=row.status,
                    date=_date_iso(row.created_at),
                )
                for row in portfolio_rows
            ],
        ),
        surveys=surveys,
    )
