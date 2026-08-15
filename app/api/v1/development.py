from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.development_models import (
    AssessmentDefinition,
    GoalReview,
    PersonalInsight,
    UserVectorProfile,
)
from app.database.models import User
from app.services import assessment_service as assessments
from app.services import development_service as dev
from app.services.assessment_catalog import ASSESSMENT_BY_CODE, STRENGTHS_DEFINITION

router = APIRouter(prefix="/development", tags=["development"])


def _checkin(row, context=None) -> dict[str, Any]:
    return {
        "id": row.id,
        "month": row.month,
        "theme": dev.checkin_theme(row),
        "status": row.status,
        "answers": dev.public_checkin_answers(row),
        "state": row.state_json or {},
        "index": row.index_value,
        "delta": row.delta_json or {},
        "insight": row.insight_json or {},
        "completed_at": row.completed_at,
        "context": {
            "factors": context.factors_json if context else [],
            "development_wants": context.development_wants_json if context else [],
        },
    }


def _goal(row, review=None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "month": row.month,
        "title": row.title,
        "experiment": row.experiment,
        "semantic_tag": row.semantic_tag,
        "status": row.status,
        "is_custom": row.is_custom,
        "review": None
        if review is None
        else {"result": review.result, "obstacle": review.obstacle, "note": review.note},
    }


async def _require_consent(session: AsyncSession, user_id: int) -> None:
    if not await dev.has_consent(session, user_id):
        raise HTTPException(status_code=403, detail="development_consent_required")


def _assessment_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if detail in {
        "assessment_not_found",
        "assessment_session_not_found",
        "assessment_question_not_found",
        "assessment_definition_not_found",
        "assessment_version_not_found",
    }:
        return HTTPException(status_code=404, detail=detail)
    if detail in {
        "assessment_methodology_not_approved",
        "assessment_version_not_seeded",
        "assessment_is_derived",
        "assessment_session_completed",
    }:
        return HTTPException(status_code=409, detail=detail)
    if detail == "assessment_age_restricted":
        return HTTPException(status_code=403, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.get("/home")
async def development_home(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await assessments.ensure_catalog(session)
    consented = await dev.has_consent(session, user.id)
    profile = await session.get(UserVectorProfile, user.id)
    checkin = await dev.get_or_create_checkin(session, user.id) if consented else None
    context = await dev.checkin_context(session, checkin.id) if checkin else None
    questions = await dev.checkin_questions(session, user.id, checkin) if checkin else dev.STATE_QUESTIONS
    goal = await dev.latest_goal(session, user.id) if consented else None
    review = (
        await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal.id)) if goal else None
    )
    return {
        "title": "Мой вектор",
        "subtitle": "Здесь нет правильных ответов. Чем честнее ты отвечаешь, тем полезнее становится твоя картина.",
        "consent_required": not consented,
        "consent_version": dev.CONSENT_VERSION,
        "profile": None
        if profile is None
        else {
            "index": profile.current_index,
            "state": profile.state_json or {},
            "baseline": profile.baseline_json or {},
            "last_checkin_at": profile.last_checkin_at,
            "notice": "Это не оценка тебя как личности. Это снимок твоего состояния сейчас.",
        },
        "current_checkin": _checkin(checkin, context) if checkin else None,
        "current_goal": _goal(goal, review),
        "questions": questions,
        "answer_options": dev.ANSWER_OPTIONS,
        "context_options": dev.CONTEXT_OPTIONS,
        "development_wants": dev.DEVELOPMENT_WANTS,
        "state_labels": dev.STATE_LABELS,
    }


class ConsentIn(BaseModel):
    accepted: bool


@router.post("/consent")
async def consent(
    payload: ConsentIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await dev.record_consent(session, user.id, payload.accepted)
    await dev.audit(
        session,
        user.id,
        "development.consent",
        metadata={"accepted": payload.accepted, "version": dev.CONSENT_VERSION},
    )
    return {"accepted": payload.accepted, "version": dev.CONSENT_VERSION}


@router.get("/assessments")
async def assessment_list(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await assessments.ensure_catalog(session)
    desired_codes = [*ASSESSMENT_BY_CODE.keys(), STRENGTHS_DEFINITION["code"]]
    definitions = {
        row.code: row
        for row in (
            await session.scalars(
                select(AssessmentDefinition).where(AssessmentDefinition.code.in_(desired_codes))
            )
        ).all()
    }
    result: list[dict[str, Any]] = []
    for code in desired_codes:
        definition = definitions.get(code)
        if definition is None:
            continue
        if code == STRENGTHS_DEFINITION["code"]:
            result.append(await assessments.strengths_payload(session, user.id))
        else:
            result.append(await assessments.definition_payload(session, definition, user_id=user.id))
    return result


@router.get("/assessments/{code}")
async def assessment_detail(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await assessments.ensure_catalog(session)
    if code == STRENGTHS_DEFINITION["code"]:
        return await assessments.strengths_payload(session, user.id)
    definition = await session.scalar(select(AssessmentDefinition).where(AssessmentDefinition.code == code))
    if definition is None or code not in ASSESSMENT_BY_CODE:
        raise HTTPException(status_code=404, detail="assessment_not_found")
    payload = await assessments.definition_payload(session, definition, user_id=user.id)
    payload["what_it_shows"] = definition.description
    payload["important"] = "Нет «лучшего типа личности». Результат не является диагнозом и не влияет на статус в ЭРА."
    return payload


@router.post("/assessments/{code}/start")
async def start_assessment(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        payload = await assessments.start_assessment(session, user, code)
    except ValueError as exc:
        raise _assessment_error(exc) from exc
    await dev.audit(
        session,
        user.id,
        "development.assessment.start",
        metadata={"assessment_code": code, "session_id": payload["id"]},
    )
    return payload


@router.get("/assessment-sessions/{assessment_session_id}")
async def assessment_session(
    assessment_session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        return await assessments.get_session_payload(session, user.id, assessment_session_id)
    except ValueError as exc:
        raise _assessment_error(exc) from exc


class AssessmentAnswerIn(BaseModel):
    question_code: str = Field(min_length=1, max_length=64)
    value: int


@router.patch("/assessment-sessions/{assessment_session_id}/answers")
async def assessment_answer(
    assessment_session_id: int,
    payload: AssessmentAnswerIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        return await assessments.save_answer(
            session,
            user.id,
            assessment_session_id,
            payload.question_code,
            payload.value,
        )
    except ValueError as exc:
        raise _assessment_error(exc) from exc


@router.post("/assessment-sessions/{assessment_session_id}/complete")
async def assessment_complete(
    assessment_session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        result = await assessments.complete_assessment(session, user.id, assessment_session_id)
    except ValueError as exc:
        raise _assessment_error(exc) from exc
    await dev.audit(
        session,
        user.id,
        "development.assessment.complete",
        metadata={
            "assessment_code": result["assessment_code"],
            "session_id": assessment_session_id,
            "methodology_version": result["version"],
        },
    )
    return result


@router.get("/assessments/{code}/result/latest")
async def latest_assessment_result(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    if code == STRENGTHS_DEFINITION["code"]:
        return await assessments.strengths_payload(session, user.id)
    definition = await assessments.get_definition(session, code)
    if definition is None or code not in ASSESSMENT_BY_CODE:
        raise HTTPException(status_code=404, detail="assessment_not_found")
    result = await assessments.latest_result(session, user.id, definition.id)
    if result is None:
        raise HTTPException(status_code=404, detail="assessment_result_not_found")
    return result


@router.get("/checkin/current")
async def current_checkin(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    row = await dev.get_or_create_checkin(session, user.id)
    context = await dev.checkin_context(session, row.id)
    return {
        **_checkin(row, context),
        "questions": await dev.checkin_questions(session, user.id, row),
        "answer_options": dev.ANSWER_OPTIONS,
        "context_options": dev.CONTEXT_OPTIONS,
        "development_wants": dev.DEVELOPMENT_WANTS,
    }


class CheckinSaveIn(BaseModel):
    answers: dict[str, int] = Field(default_factory=dict)
    factors: list[str] | None = None
    development_wants: list[str] | None = None


@router.patch("/checkin/current/answers")
async def save_current_checkin(
    payload: CheckinSaveIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    row = await dev.get_or_create_checkin(session, user.id)
    try:
        await dev.save_checkin(
            session, row, payload.answers, payload.factors, payload.development_wants
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _checkin(row, await dev.checkin_context(session, row.id))


@router.post("/checkin/current/complete")
async def complete_current_checkin(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    row = await dev.get_or_create_checkin(session, user.id)
    try:
        await dev.complete_checkin(session, row)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await dev.audit(
        session,
        user.id,
        "development.checkin.complete",
        metadata={"month": row.month, "checkin_id": row.id},
    )
    return _checkin(row, await dev.checkin_context(session, row.id))


@router.get("/vector")
async def vector(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    profile = await session.get(UserVectorProfile, user.id)
    if profile is None:
        return {"index": None, "state": {}, "baseline": {}, "last_checkin_at": None}
    return {
        "index": profile.current_index,
        "state": profile.state_json or {},
        "baseline": profile.baseline_json or {},
        "last_checkin_at": profile.last_checkin_at,
        "notice": "Стабильные черты личности и интересы не входят в этот показатель.",
    }


@router.get("/history")
async def history(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await _require_consent(session, user.id)
    return [_checkin(row) for row in await dev.list_history(session, user.id)]


@router.get("/goals/current")
async def current_goal(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any] | None:
    await _require_consent(session, user.id)
    goal = await dev.latest_goal(session, user.id)
    if goal is None:
        return None
    return _goal(
        goal, await session.scalar(select(GoalReview).where(GoalReview.goal_id == goal.id))
    )


class GoalIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    experiment: str | None = Field(default=None, max_length=2000)
    semantic_tag: str | None = Field(default=None, max_length=64)
    is_custom: bool = False


@router.post("/goals")
async def create_goal(
    payload: GoalIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    return (
        _goal(
            await dev.create_goal(
                session,
                user.id,
                payload.title,
                payload.experiment,
                payload.semantic_tag,
                payload.is_custom,
            )
        )
        or {}
    )


class GoalReviewIn(BaseModel):
    result: str
    obstacle: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/goals/{goal_id}/review")
async def review_goal(
    goal_id: int,
    payload: GoalReviewIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        review = await dev.review_goal(
            session, user.id, goal_id, payload.result, payload.obstacle, payload.note
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if str(exc) == "goal_not_found" else 422, detail=str(exc)
        ) from exc
    return {
        "goal_id": goal_id,
        "result": review.result,
        "obstacle": review.obstacle,
        "note": review.note,
    }


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    checkin_id: int | None = None


@router.post("/notes")
async def add_note(
    payload: NoteIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        row = await dev.save_note(session, user.id, payload.checkin_id, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": row.id, "created_at": row.created_at}


@router.get("/notes/remember")
async def remembered_notes(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await _require_consent(session, user.id)
    rows = await dev.due_personal_notes(session, user.id)
    return [
        {"id": row.id, "text": row.text, "created_at": row.created_at, "checkin_id": row.checkin_id}
        for row in rows
    ]


class PulseIn(BaseModel):
    energy: int


@router.post("/pulse")
async def pulse(
    payload: PulseIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        row = await dev.save_weekly_pulse(session, user.id, payload.energy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"week_start": row.week_start, "energy": row.energy}


@router.get("/privacy")
async def privacy(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    settings = await dev.visibility_settings(session, user.id)
    return {
        "consent_version": dev.CONSENT_VERSION,
        "admin_visibility": {
            "summary": settings.summary_visible,
            "interests": settings.interests_visible,
            "goals": settings.goals_visible,
        },
        "admin_can_see": [
            "итоговые разрешённые показатели состояния",
            "динамику",
            "интересы после пройденных исследований",
            "выбранные направления развития",
            "текущий фокус",
            "дату последнего Check-in",
        ],
        "private_only": [
            "личные заметки",
            "свободные записи",
            "черновики",
            "скрытые выводы",
            "дословные чувствительные ответы",
        ],
    }


class PrivacyIn(BaseModel):
    summary: bool
    interests: bool
    goals: bool


@router.patch("/privacy")
async def update_privacy(
    payload: PrivacyIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = await dev.visibility_settings(session, user.id)
    settings.summary_visible = payload.summary
    settings.interests_visible = payload.interests
    settings.goals_visible = payload.goals
    await dev.audit(session, user.id, "development.privacy.update")
    return {
        "summary": settings.summary_visible,
        "interests": settings.interests_visible,
        "goals": settings.goals_visible,
    }


@router.get("/insights")
async def insights(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await _require_consent(session, user.id)
    rows = (
        await session.scalars(
            select(PersonalInsight)
            .where(PersonalInsight.user_id == user.id, PersonalInsight.hidden.is_(False))
            .order_by(desc(PersonalInsight.created_at))
        )
    ).all()
    return [
        {
            "id": row.id,
            "text": row.text,
            "semantic_tag": row.semantic_tag,
            "accepted": row.accepted,
            "created_at": row.created_at,
        }
        for row in rows
    ]


class InsightFeedbackIn(BaseModel):
    accepted: bool


@router.post("/insights/{insight_id}/feedback")
async def insight_feedback(
    insight_id: int,
    payload: InsightFeedbackIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_consent(session, user.id)
    try:
        row = await dev.set_insight_feedback(session, user.id, insight_id, payload.accepted)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await dev.audit(
        session,
        user.id,
        "development.insight.feedback",
        metadata={"insight_id": insight_id, "accepted": payload.accepted},
    )
    return {"id": row.id, "accepted": row.accepted, "hidden": row.hidden}
