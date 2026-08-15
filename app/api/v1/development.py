from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.development_models import AssessmentDefinition, GoalReview, PersonalInsight, UserVectorProfile
from app.database.models import User
from app.services import development_service as dev

router = APIRouter(prefix="/development", tags=["development"])


def _assessment(row: AssessmentDefinition) -> dict[str, Any]:
    return {"code":row.code,"title":row.title,"description":row.description,"source":row.source,"methodology":row.methodology,"license":row.license,"license_status":row.license_status,"estimated_minutes":row.estimated_minutes,"min_age":row.min_age,"recommended_retake_after_days":row.recommended_retake_after_days,"construct_type":row.construct_type,"available":row.license_status in {"approved","available_after_data"}}


def _checkin(row, context=None) -> dict[str, Any]:
    return {"id":row.id,"month":row.month,"status":row.status,"answers":row.answers_json or {},"state":row.state_json or {},"index":row.index_value,"delta":row.delta_json or {},"insight":row.insight_json or {},"completed_at":row.completed_at,"context":{"factors":context.factors_json if context else [],"development_wants":context.development_wants_json if context else []}}


def _goal(row, review=None) -> dict[str, Any] | None:
    if row is None: return None
    return {"id":row.id,"month":row.month,"title":row.title,"experiment":row.experiment,"semantic_tag":row.semantic_tag,"status":row.status,"is_custom":row.is_custom,"review":None if review is None else {"result":review.result,"obstacle":review.obstacle,"note":review.note}}


async def _require_consent(session: AsyncSession, user_id: int) -> None:
    if not await dev.has_consent(session,user_id): raise HTTPException(status_code=403,detail="development_consent_required")


@router.get("/home")
async def development_home(user: User=Depends(get_current_user),session: AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await dev.ensure_methodology_catalog(session); consented=await dev.has_consent(session,user.id); profile=await session.get(UserVectorProfile,user.id); checkin=await dev.get_or_create_checkin(session,user.id) if consented else None; context=await dev.checkin_context(session,checkin.id) if checkin else None; goal=await dev.latest_goal(session,user.id) if consented else None; review=await session.scalar(select(GoalReview).where(GoalReview.goal_id==goal.id)) if goal else None
    return {"title":"Мой вектор","subtitle":"Здесь нет правильных ответов. Чем честнее ты отвечаешь, тем полезнее становится твоя картина.","consent_required":not consented,"consent_version":dev.CONSENT_VERSION,"profile":None if profile is None else {"index":profile.current_index,"state":profile.state_json or {},"baseline":profile.baseline_json or {},"last_checkin_at":profile.last_checkin_at,"notice":"Это не оценка тебя как личности. Это снимок твоего состояния сейчас."},"current_checkin":_checkin(checkin,context) if checkin else None,"current_goal":_goal(goal,review),"questions":dev.STATE_QUESTIONS,"answer_options":dev.ANSWER_OPTIONS,"context_options":dev.CONTEXT_OPTIONS,"development_wants":dev.DEVELOPMENT_WANTS,"state_labels":dev.STATE_LABELS}


class ConsentIn(BaseModel): accepted: bool
@router.post("/consent")
async def consent(payload:ConsentIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await dev.record_consent(session,user.id,payload.accepted); await dev.audit(session,user.id,"development.consent",metadata={"accepted":payload.accepted,"version":dev.CONSENT_VERSION}); return {"accepted":payload.accepted,"version":dev.CONSENT_VERSION}


@router.get("/assessments")
async def assessments(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> list[dict[str,Any]]:
    del user; await dev.ensure_methodology_catalog(session); rows=(await session.scalars(select(AssessmentDefinition).where(AssessmentDefinition.active.is_(True)).order_by(AssessmentDefinition.id))).all(); return [_assessment(row) for row in rows]


@router.get("/assessments/{code}")
async def assessment_detail(code:str,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    del user; await dev.ensure_methodology_catalog(session); row=await session.scalar(select(AssessmentDefinition).where(AssessmentDefinition.code==code))
    if row is None: raise HTTPException(status_code=404,detail="assessment_not_found")
    return {**_assessment(row),"what_it_shows":row.description,"important":"Нет «лучшего типа личности». Результат не является диагнозом.","release_gate":"Перед запуском вопросов должны быть зафиксированы точная версия, scoring, лицензия и валидированная русская формулировка." if row.license_status=="methodology_review" else None}


@router.post("/assessments/{code}/start")
async def start_assessment(code:str,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id); await dev.ensure_methodology_catalog(session); row=await session.scalar(select(AssessmentDefinition).where(AssessmentDefinition.code==code))
    if row is None: raise HTTPException(status_code=404,detail="assessment_not_found")
    if row.license_status!="approved": raise HTTPException(status_code=409,detail="assessment_methodology_not_approved")
    raise HTTPException(status_code=409,detail="assessment_version_not_seeded")


@router.get("/checkin/current")
async def current_checkin(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id); row=await dev.get_or_create_checkin(session,user.id); context=await dev.checkin_context(session,row.id); return {**_checkin(row,context),"questions":dev.STATE_QUESTIONS,"answer_options":dev.ANSWER_OPTIONS,"context_options":dev.CONTEXT_OPTIONS,"development_wants":dev.DEVELOPMENT_WANTS}


class CheckinSaveIn(BaseModel):
    answers: dict[str,int]=Field(default_factory=dict); factors:list[str]|None=None; development_wants:list[str]|None=None
@router.patch("/checkin/current/answers")
async def save_current_checkin(payload:CheckinSaveIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id); row=await dev.get_or_create_checkin(session,user.id)
    try: await dev.save_checkin(session,row,payload.answers,payload.factors,payload.development_wants)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    return _checkin(row,await dev.checkin_context(session,row.id))


@router.post("/checkin/current/complete")
async def complete_current_checkin(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id); row=await dev.get_or_create_checkin(session,user.id)
    try: await dev.complete_checkin(session,row)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    await dev.audit(session,user.id,"development.checkin.complete",metadata={"month":row.month,"checkin_id":row.id}); return _checkin(row,await dev.checkin_context(session,row.id))


@router.get("/vector")
async def vector(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id); profile=await session.get(UserVectorProfile,user.id)
    if profile is None: return {"index":None,"state":{},"baseline":{},"last_checkin_at":None}
    return {"index":profile.current_index,"state":profile.state_json or {},"baseline":profile.baseline_json or {},"last_checkin_at":profile.last_checkin_at,"notice":"Стабильные черты личности и интересы не входят в этот показатель."}


@router.get("/history")
async def history(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> list[dict[str,Any]]:
    await _require_consent(session,user.id); return [_checkin(row) for row in await dev.list_history(session,user.id)]


@router.get("/goals/current")
async def current_goal(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]|None:
    await _require_consent(session,user.id); goal=await dev.latest_goal(session,user.id)
    if goal is None: return None
    return _goal(goal,await session.scalar(select(GoalReview).where(GoalReview.goal_id==goal.id)))


class GoalIn(BaseModel):
    title:str=Field(min_length=2,max_length=255); experiment:str|None=Field(default=None,max_length=2000); semantic_tag:str|None=Field(default=None,max_length=64); is_custom:bool=False
@router.post("/goals")
async def create_goal(payload:GoalIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id); return _goal(await dev.create_goal(session,user.id,payload.title,payload.experiment,payload.semantic_tag,payload.is_custom)) or {}


class GoalReviewIn(BaseModel):
    result:str; obstacle:str|None=Field(default=None,max_length=64); note:str|None=Field(default=None,max_length=2000)
@router.post("/goals/{goal_id}/review")
async def review_goal(goal_id:int,payload:GoalReviewIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id)
    try: review=await dev.review_goal(session,user.id,goal_id,payload.result,payload.obstacle,payload.note)
    except ValueError as exc: raise HTTPException(status_code=404 if str(exc)=="goal_not_found" else 422,detail=str(exc)) from exc
    return {"goal_id":goal_id,"result":review.result,"obstacle":review.obstacle,"note":review.note}


class NoteIn(BaseModel):
    text:str=Field(min_length=1,max_length=5000); checkin_id:int|None=None
@router.post("/notes")
async def add_note(payload:NoteIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id)
    try: row=await dev.save_note(session,user.id,payload.checkin_id,payload.text)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
    return {"id":row.id,"created_at":row.created_at}


class PulseIn(BaseModel): energy:int
@router.post("/pulse")
async def pulse(payload:PulseIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    await _require_consent(session,user.id)
    try: row=await dev.save_weekly_pulse(session,user.id,payload.energy)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    return {"week_start":row.week_start,"energy":row.energy}


@router.get("/privacy")
async def privacy(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    settings=await dev.visibility_settings(session,user.id); return {"consent_version":dev.CONSENT_VERSION,"admin_visibility":{"summary":settings.summary_visible,"interests":settings.interests_visible,"goals":settings.goals_visible},"admin_can_see":["итоговые разрешённые показатели состояния","динамику","интересы после утверждённых методик","выбранные направления развития","текущий фокус","дату последнего Check-in"],"private_only":["личные заметки","свободные записи","черновики","скрытые выводы","дословные чувствительные ответы"]}


class PrivacyIn(BaseModel): summary:bool; interests:bool; goals:bool
@router.patch("/privacy")
async def update_privacy(payload:PrivacyIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> dict[str,Any]:
    settings=await dev.visibility_settings(session,user.id); settings.summary_visible=payload.summary; settings.interests_visible=payload.interests; settings.goals_visible=payload.goals; await dev.audit(session,user.id,"development.privacy.update"); return {"summary":settings.summary_visible,"interests":settings.interests_visible,"goals":settings.goals_visible}


@router.get("/insights")
async def insights(user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)) -> list[dict[str,Any]]:
    await _require_consent(session,user.id); rows=(await session.scalars(select(PersonalInsight).where(PersonalInsight.user_id==user.id,PersonalInsight.hidden.is_(False)).order_by(desc(PersonalInsight.created_at)))).all(); return [{"id":row.id,"text":row.text,"semantic_tag":row.semantic_tag,"accepted":row.accepted,"created_at":row.created_at} for row in rows]
