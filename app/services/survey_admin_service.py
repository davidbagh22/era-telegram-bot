from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import AdminSurvey, AdminSurveyResponse
from app.database.models import User
from app.services.survey_service import (
    MONTHLY_SURVEY_DESCRIPTION,
    MONTHLY_SURVEY_QUESTIONS,
    MONTHLY_SURVEY_TITLE,
    questions_payload,
)
from app.utils.constants import ApplicationStatus

# Admin-side survey management — the Mini App equivalent of
# app/handlers/admin/surveys_analytics.py (list/create/edit/send/archive,
# results). Excel export of surveys/analytics is not ported yet — it
# remains a Bot-only capability (docs/ERA_PLATFORM_PROGRESS.md tracks
# this as the last one before a Bot admin-cleanup pass).


async def list_surveys(session: AsyncSession, *, include_archived: bool = False) -> list[AdminSurvey]:
    conditions = [] if include_archived else [AdminSurvey.status != "archived"]
    return list(
        (
            await session.scalars(
                select(AdminSurvey)
                .where(*conditions)
                .order_by(AdminSurvey.created_at.desc(), AdminSurvey.id.desc())
            )
        ).all()
    )


async def response_count(session: AsyncSession, survey_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(AdminSurveyResponse).where(AdminSurveyResponse.survey_id == survey_id)
        )
        or 0
    )


async def get_or_create_monthly_survey(session: AsyncSession, *, created_by_id: int | None) -> AdminSurvey:
    survey = await session.scalar(
        select(AdminSurvey)
        .where(AdminSurvey.is_monthly.is_(True), AdminSurvey.status != "archived")
        .order_by(AdminSurvey.created_at.desc(), AdminSurvey.id.desc())
    )
    if survey:
        return survey
    survey = AdminSurvey(
        title=MONTHLY_SURVEY_TITLE,
        description=MONTHLY_SURVEY_DESCRIPTION,
        questions_json=questions_payload(MONTHLY_SURVEY_QUESTIONS),
        audience_type="approved",
        audience_filter_json={},
        status="draft",
        is_monthly=True,
        created_by=created_by_id,
    )
    session.add(survey)
    await session.flush()
    return survey


async def create_survey(
    session: AsyncSession, *, title: str, description: str | None, questions: list[str], created_by_id: int | None
) -> AdminSurvey:
    survey = AdminSurvey(
        title=title,
        description=description,
        questions_json=questions_payload(questions),
        audience_type="approved",
        audience_filter_json={},
        status="draft",
        is_monthly=False,
        created_by=created_by_id,
    )
    session.add(survey)
    await session.flush()
    return survey


def update_survey(
    survey: AdminSurvey, *, title: str, description: str | None, questions: list[str], updated_by_id: int | None
) -> None:
    survey.title = title
    survey.description = description
    survey.questions_json = questions_payload(questions)
    survey.updated_by = updated_by_id


def archive_survey(survey: AdminSurvey, *, updated_by_id: int | None) -> None:
    survey.status = "archived"
    survey.updated_by = updated_by_id


async def send_recipients(session: AsyncSession) -> list[User]:
    """Every approved, non-blocked, non-archived participant — mirrors the
    Bot's own recipient query in surveys_analytics.py::send_survey."""
    return list(
        (
            await session.scalars(
                select(User).where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_blocked.is_(False),
                    User.is_archived.is_(False),
                )
            )
        ).all()
    )


def mark_sent(survey: AdminSurvey, *, timezone_name: str, updated_by_id: int | None) -> None:
    now = datetime.now(ZoneInfo(timezone_name))
    survey.status = "sent"
    survey.sent_at = now
    if survey.is_monthly:
        survey.last_sent_month = now.strftime("%Y-%m")
    survey.updated_by = updated_by_id


async def list_responses(session: AsyncSession, survey_id: int) -> list[tuple[AdminSurveyResponse, User]]:
    result = await session.execute(
        select(AdminSurveyResponse, User)
        .join(User, User.id == AdminSurveyResponse.user_id)
        .where(AdminSurveyResponse.survey_id == survey_id)
        .order_by(AdminSurveyResponse.created_at.desc())
    )
    return list(result.all())
