from __future__ import annotations

from datetime import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_settings, get_bot
from app.api.v1.admin_executive_export import require_admin
from app.database.leadership_models import WeeklyPulseSchedule
from app.database.models import User
from app.services.weekly_pulse_cycle_service import (
    WeeklyPulseConfigurationError,
    get_schedule,
    update_schedule,
)

router = APIRouter(prefix="/admin/leadership/weekly-pulse", tags=["admin-weekly-pulse"])


class WeeklyPulseScheduleIn(BaseModel):
    enabled: bool = True
    open_weekday: int = Field(ge=0, le=6)
    open_time: time
    deadline_hours: int = Field(ge=1, le=168)
    first_reminder_hours: int = Field(ge=0, le=168)
    final_reminder_hours: int = Field(ge=1, le=168)
    report_weekday: int = Field(ge=0, le=6)
    timezone: str = Field(min_length=1, max_length=64)


class WeeklyPulseScheduleOut(WeeklyPulseScheduleIn):
    id: int


def _as_out(schedule: WeeklyPulseSchedule) -> WeeklyPulseScheduleOut:
    return WeeklyPulseScheduleOut(
        id=schedule.id,
        enabled=schedule.enabled,
        open_weekday=schedule.open_weekday,
        open_time=schedule.open_time,
        deadline_hours=schedule.deadline_hours,
        first_reminder_hours=schedule.first_reminder_hours,
        final_reminder_hours=schedule.final_reminder_hours,
        report_weekday=schedule.report_weekday,
        timezone=schedule.timezone,
    )


@router.get("/schedule", response_model=WeeklyPulseScheduleOut)
async def read_weekly_pulse_schedule(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WeeklyPulseScheduleOut:
    schedule = await get_schedule(session)
    await session.commit()
    return _as_out(schedule)


@router.put("/schedule", response_model=WeeklyPulseScheduleOut)
async def save_weekly_pulse_schedule(
    payload: WeeklyPulseScheduleIn,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WeeklyPulseScheduleOut:
    try:
        schedule = await update_schedule(
            session,
            enabled=payload.enabled,
            open_weekday=payload.open_weekday,
            open_time=payload.open_time,
            deadline_hours=payload.deadline_hours,
            first_reminder_hours=payload.first_reminder_hours,
            final_reminder_hours=payload.final_reminder_hours,
            report_weekday=payload.report_weekday,
            timezone_name=payload.timezone,
        )
    except WeeklyPulseConfigurationError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _as_out(schedule)


@router.get("/cycles")
async def list_cycles(
    _admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)
):
    from sqlalchemy import select
    from app.database.leadership_models import WeeklyPulseCycle, WeeklyPulseArchive

    rows = (
        await session.execute(
            select(WeeklyPulseCycle, WeeklyPulseArchive.id)
            .outerjoin(
                WeeklyPulseArchive, WeeklyPulseArchive.cycle_id == WeeklyPulseCycle.id
            )
            .order_by(WeeklyPulseCycle.date_from.desc())
            .limit(52)
        )
    ).all()
    return [
        {
            "id": c.id,
            "week_number": c.week_number,
            "date_from": str(c.date_from),
            "date_to": str(c.date_to),
            "status": c.status,
            "eligible_count": c.eligible_count,
            "submitted_count": c.submitted_count,
            "deadline_at": c.deadline_at.isoformat(),
            "archive_id": a,
        }
        for c, a in rows
    ]


@router.post("/cycles/{cycle_id}/archive")
async def create_archive(
    cycle_id: int,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timezone
    from app.database.leadership_models import WeeklyPulseCycle
    from app.services.weekly_pulse_archive_service import freeze_week

    cycle = await session.get(WeeklyPulseCycle, cycle_id)
    if cycle is None:
        raise HTTPException(404, "pulse_cycle_not_found")
    deadline = cycle.deadline_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) < deadline:
        raise HTTPException(409, "pulse_cycle_still_open")
    archived = await freeze_week(session, cycle)
    await session.commit()
    return {"id": archived.id, "snapshot": archived.snapshot}


@router.get("/archives/{archive_id}")
async def read_archive(
    archive_id: int,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from app.database.leadership_models import WeeklyPulseArchive

    archived = await session.get(WeeklyPulseArchive, archive_id)
    if archived is None:
        raise HTTPException(404, "pulse_archive_not_found")
    return {"id": archived.id, "snapshot": archived.snapshot}


@router.get("/archives/{archive_id}/document")
async def download_archive(
    archive_id: int,
    format: str = "docx",
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from fastapi import Response
    from starlette.concurrency import run_in_threadpool
    from app.database.leadership_models import WeeklyPulseArchive
    from app.services.weekly_pulse_archive_service import render_docx, render_pdf

    if format not in {"docx", "pdf"}:
        raise HTTPException(422, "unsupported_format")
    archived = await session.get(WeeklyPulseArchive, archive_id)
    if archived is None:
        raise HTTPException(404, "pulse_archive_not_found")
    snapshot = archived.snapshot
    content = archived.docx_data if format == "docx" else archived.pdf_data
    if not content:
        content = await run_in_threadpool(render_docx if format == "docx" else render_pdf, snapshot)
    mime = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if format == "docx"
        else "application/pdf"
    )
    name = f"ERA_PULSE_{snapshot['year']}_W{snapshot['week']:02d}.{format}"
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/forum")
async def forum_status(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings=Depends(get_settings),
):
    from app.services.leaders_topics_service import topic_id

    if not settings.leaders_chat_id:
        return {"configured": False, "topics": {}}
    return {
        "configured": True,
        "topics": {
            key: await topic_id(session, settings.leaders_chat_id, key)
            for key in ("tasks", "pulse", "important")
        },
    }


class PulseQuestionIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    text: str = Field(min_length=3, max_length=300)
    required: bool = False
    audience: str = Field(default="all", pattern=r"^(all|chairman|head|external|internal|media)$")
    is_active: bool = True
    choices: list[str] = Field(default_factory=list, max_length=8)
    condition_key: str | None = None
    condition_value: str | None = None


class PulseQuestionsIn(BaseModel):
    questions: list[PulseQuestionIn] = Field(min_length=1, max_length=40)


@router.get("/questions")
async def read_questions(
    _admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)
):
    from app.services.pulse_questionnaire_service import questions

    return await questions(session)


@router.put("/questions")
async def save_questions(
    payload: PulseQuestionsIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    import json
    from sqlalchemy import select
    from app.database.models import AppSetting
    from app.services.audit_service import audit

    if len({q.key for q in payload.questions}) != len(payload.questions):
        raise HTTPException(422, "duplicate_question_keys")
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == "weekly_pulse_questions")
    )
    old = json.loads(row.value) if row else None
    value = [q.model_dump() for q in payload.questions]
    if row is None:
        row = AppSetting(
            key="weekly_pulse_questions",
            value=json.dumps(value, ensure_ascii=False),
            updated_by=admin.id,
        )
        session.add(row)
    else:
        row.value = json.dumps(value, ensure_ascii=False)
        row.updated_by = admin.id
    await audit(
        session,
        actor_id=admin.id,
        action="weekly_pulse.questions_updated",
        entity_type="app_setting",
        old_value={"questions": old},
        new_value={"questions": value},
    )
    await session.commit()
    return value


@router.get('/cycles/{cycle_id}/participants')
async def participants(cycle_id:int,_admin:User=Depends(require_admin),session=Depends(get_session)):
    from app.database.leadership_models import WeeklyPulseCycle, WeeklyPulseParticipant
    from app.services.weekly_pulse_cycle_service import sync_cycle_participants
    from app.database.models import LeadershipReport
    from app.database.leadership_models import LeadershipReportPulse
    from sqlalchemy import select
    cycle=await session.get(WeeklyPulseCycle,cycle_id)
    if not cycle: raise HTTPException(404,'cycle_not_found')
    rows=await sync_cycle_participants(session,cycle) if cycle.status not in {'completed','archived'} else (await session.scalars(select(WeeklyPulseParticipant).where(WeeklyPulseParticipant.cycle_id==cycle.id))).all()
    result=[]
    for row in rows:
        user=await session.get(User,row.user_id) if row.user_id else None
        report=await session.scalar(select(LeadershipReport).where(LeadershipReport.pulse_cycle_id==cycle_id,LeadershipReport.owner_id==row.user_id)) if row.user_id else None
        pulse=await session.scalar(select(LeadershipReportPulse).where(LeadershipReportPulse.report_id==report.id)) if report else None
        result.append({'id':row.id,'user_id':row.user_id,'name':f'{user.first_name} {user.last_name or ""}'.strip() if user else 'Участник ещё не зарегистрирован',
            'status':row.status,'connected':user is not None,'answers':(pulse.answers_json or {}).get('submitted',{}) if pulse else {}})
    await session.commit()
    return result


class ParticipantAction(BaseModel):
    action: str = Field(pattern=r'^(excused|excluded|included|remind)$')


@router.post('/participants/{participant_id}')
async def participant_action(participant_id:int,payload:ParticipantAction,admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    from app.database.leadership_models import WeeklyPulseParticipant,WeeklyPulseCycle
    from app.services.audit_service import audit
    row=await session.get(WeeklyPulseParticipant,participant_id)
    if not row: raise HTTPException(404,'participant_not_found')
    cycle=await session.get(WeeklyPulseCycle,row.cycle_id)
    if cycle.status in {'completed','archived'}: raise HTTPException(409,'Неделя уже закрыта')
    if payload.action=='remind':
        from app.services.bot_notification_service import send_bot_notification,PrimaryAction
        from datetime import datetime,timezone
        if not bot: raise HTTPException(503,'Бот временно недоступен')
        info=await bot.get_me()
        await send_bot_notification(bot,row.telegram_user_id,title="Напоминание: Пульс ЭРА",body="Заполните итоги текущей недели.",
            settings=settings,delivery_key=f'pulse-manual:{row.id}:{datetime.now(timezone.utc).strftime("%Y%m%d%H")}',notification_type='pulse_manual',
            action=PrimaryAction(label="Заполнить",url=f'https://t.me/{info.username}?start=pulse_connect'))
    else: row.override=payload.action
    await audit(session,actor_id=admin.id,action='pulse.participant_'+payload.action,entity_type='weekly_pulse_participant',entity_id=row.id)
    await session.commit()
    return {'ok':True}
