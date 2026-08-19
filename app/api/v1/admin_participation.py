from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.database.participation_models import ParticipationLifecycle
from app.services.authorization_service import is_full_admin
from app.services.participation_lifecycle_service import (
    ACTIVITY_STATES,
    MODE_ACTIVE,
    MODE_EXITED,
    MODE_LIGHT,
    PARTICIPATION_MODES,
    sync_lifecycle_state,
)
from app.utils.constants import ApplicationStatus

router = APIRouter(prefix="/admin/participation", tags=["admin-participation"])


class ParticipationPersonOut(BaseModel):
    id: int
    telegram_id: int
    name: str
    username: str | None
    participation_mode: str
    activity_state: str
    last_meaningful_at: str | None
    state_since: str | None
    pause_until: str | None
    returned_at: str | None


class ParticipationSummaryOut(BaseModel):
    historical_approved: int
    current_roster: int
    active_base: int
    returned_30d: int
    new_30d: int
    modes: dict[str, int]
    states: dict[str, int]


def _require_admin(user: User, settings: Settings) -> None:
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")


async def _ensure_rows(session: AsyncSession) -> None:
    await sync_lifecycle_state(session, now=datetime.now(timezone.utc))


@router.get("/summary", response_model=ParticipationSummaryOut)
async def read_participation_summary(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> ParticipationSummaryOut:
    _require_admin(user, settings)
    await _ensure_rows(session)
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)

    historical_approved = int(
        await session.scalar(
            select(func.count(User.id)).where(
                User.application_status == ApplicationStatus.APPROVED
            )
        )
        or 0
    )
    current_roster = int(
        await session.scalar(
            select(func.count(User.id))
            .join(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                User.is_blocked.is_(False),
                ParticipationLifecycle.participation_mode != MODE_EXITED,
            )
        )
        or 0
    )
    active_base = int(
        await session.scalar(
            select(func.count(User.id))
            .join(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                User.is_blocked.is_(False),
                ParticipationLifecycle.participation_mode.in_([MODE_ACTIVE, MODE_LIGHT]),
                ParticipationLifecycle.activity_state == "ACTIVE",
            )
        )
        or 0
    )
    returned_30d = int(
        await session.scalar(
            select(func.count(User.id))
            .join(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                ParticipationLifecycle.returned_at.is_not(None),
                ParticipationLifecycle.returned_at >= month_ago,
            )
        )
        or 0
    )
    new_30d = int(
        await session.scalar(
            select(func.count(User.id)).where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                User.is_blocked.is_(False),
                User.created_at >= month_ago,
            )
        )
        or 0
    )

    mode_rows = (
        await session.execute(
            select(ParticipationLifecycle.participation_mode, func.count())
            .join(User, User.id == ParticipationLifecycle.user_id)
            .where(User.application_status == ApplicationStatus.APPROVED)
            .group_by(ParticipationLifecycle.participation_mode)
        )
    ).all()
    state_rows = (
        await session.execute(
            select(ParticipationLifecycle.activity_state, func.count())
            .join(User, User.id == ParticipationLifecycle.user_id)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                User.is_blocked.is_(False),
                ParticipationLifecycle.participation_mode != MODE_EXITED,
            )
            .group_by(ParticipationLifecycle.activity_state)
        )
    ).all()
    modes = {mode: 0 for mode in sorted(PARTICIPATION_MODES)}
    states = {state: 0 for state in sorted(ACTIVITY_STATES)}
    modes.update({str(key): int(value) for key, value in mode_rows})
    states.update({str(key): int(value) for key, value in state_rows})
    return ParticipationSummaryOut(
        historical_approved=historical_approved,
        current_roster=current_roster,
        active_base=active_base,
        returned_30d=returned_30d,
        new_30d=new_30d,
        modes=modes,
        states=states,
    )


@router.get("/people", response_model=list[ParticipationPersonOut])
async def read_participation_people(
    state: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    returned_30d: bool = Query(default=False),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> list[ParticipationPersonOut]:
    _require_admin(user, settings)
    await _ensure_rows(session)
    if state is not None:
        state = state.upper()
        if state not in ACTIVITY_STATES:
            raise HTTPException(status_code=422, detail="invalid_activity_state")
    if mode is not None:
        mode = mode.upper()
        if mode not in PARTICIPATION_MODES:
            raise HTTPException(status_code=422, detail="invalid_participation_mode")

    conditions = [User.application_status == ApplicationStatus.APPROVED]
    if state:
        conditions.append(ParticipationLifecycle.activity_state == state)
    if mode:
        conditions.append(ParticipationLifecycle.participation_mode == mode)
    if returned_30d:
        conditions.extend(
            [
                ParticipationLifecycle.returned_at.is_not(None),
                ParticipationLifecycle.returned_at >= datetime.now(timezone.utc) - timedelta(days=30),
            ]
        )

    rows = (
        await session.execute(
            select(User, ParticipationLifecycle)
            .join(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(*conditions)
            .order_by(User.first_name, User.last_name, User.id)
        )
    ).all()
    return [
        ParticipationPersonOut(
            id=member.id,
            telegram_id=member.telegram_id,
            name=f"{member.first_name} {member.last_name or ''}".strip(),
            username=member.username,
            participation_mode=lifecycle.participation_mode,
            activity_state=lifecycle.activity_state,
            last_meaningful_at=(
                lifecycle.last_meaningful_at.isoformat() if lifecycle.last_meaningful_at else None
            ),
            state_since=lifecycle.state_since.isoformat() if lifecycle.state_since else None,
            pause_until=lifecycle.pause_until.isoformat() if lifecycle.pause_until else None,
            returned_at=lifecycle.returned_at.isoformat() if lifecycle.returned_at else None,
        )
        for member, lifecycle in rows
    ]
