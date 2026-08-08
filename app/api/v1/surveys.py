from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.management_models import AdminSurvey
from app.database.models import User
from app.services import survey_service

# Participant-facing surveys — the Mini App equivalent of
# app/handlers/participant/surveys.py. The Bot answers one question at a
# time in chat; the Mini App collects every answer in a single form and
# submits them all at once (see SubmitIn below).

router = APIRouter(prefix="/surveys", tags=["surveys"])


class SurveyOut(BaseModel):
    id: int
    title: str
    description: str | None
    questions: list[str]
    completed: bool


async def _to_survey_out(session: AsyncSession, survey: AdminSurvey, user: User) -> SurveyOut:
    response = await survey_service.get_response(session, survey.id, user.id)
    return SurveyOut(
        id=survey.id,
        title=survey.title,
        description=survey.description,
        questions=survey_service.survey_questions(survey),
        completed=response is not None,
    )


class SurveyDetailOut(SurveyOut):
    answers: list[str] | None = None


@router.get("", response_model=list[SurveyOut])
async def list_surveys(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SurveyOut]:
    surveys = await survey_service.list_visible_surveys(session)
    return [await _to_survey_out(session, survey, user) for survey in surveys]


async def _get_visible_survey(session: AsyncSession, survey_id: int) -> AdminSurvey:
    survey = await session.get(AdminSurvey, survey_id)
    if survey is None or survey.status not in survey_service.PARTICIPANT_VISIBLE_STATUSES:
        raise HTTPException(status_code=404, detail="survey_not_found")
    return survey


@router.get("/{survey_id}", response_model=SurveyDetailOut)
async def read_survey(
    survey_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SurveyDetailOut:
    survey = await _get_visible_survey(session, survey_id)
    out = await _to_survey_out(session, survey, user)
    response = await survey_service.get_response(session, survey.id, user.id)
    answers = [item["answer"] for item in survey_service.answer_items(response)] if response else None
    return SurveyDetailOut(**out.model_dump(), answers=answers)


class SubmitIn(BaseModel):
    answers: list[str]


@router.post("/{survey_id}/submit", response_model=SurveyOut)
async def submit_survey(
    survey_id: int,
    payload: SubmitIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SurveyOut:
    survey = await _get_visible_survey(session, survey_id)
    questions = survey_service.survey_questions(survey)
    answers = [a.strip() for a in payload.answers]
    if len(answers) != len(questions) or any(not a for a in answers):
        raise HTTPException(status_code=422, detail="all_answers_required")
    await survey_service.submit_survey(session, survey, user, answers)
    return await _to_survey_out(session, survey, user)
