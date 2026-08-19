from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services.digital_engagement_service import (
    award_material_acknowledgement,
    configured_important_materials,
    digital_monthly_cap,
    digital_points_this_month,
)

router = APIRouter(prefix="/engagement", tags=["engagement"])


class ImportantMaterialOut(BaseModel):
    key: str
    version: str
    title: str


class MaterialAcknowledgeIn(BaseModel):
    version: str


class DigitalCapOut(BaseModel):
    earned: int
    cap: int
    remaining: int


@router.get("/digital-cap", response_model=DigitalCapOut)
async def read_digital_cap(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DigitalCapOut:
    cap = await digital_monthly_cap(session)
    earned = await digital_points_this_month(session, user.id)
    return DigitalCapOut(earned=earned, cap=cap, remaining=max(cap - earned, 0))


@router.get("/important-materials", response_model=list[ImportantMaterialOut])
async def read_important_materials(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ImportantMaterialOut]:
    return [ImportantMaterialOut(**item) for item in await configured_important_materials(session)]


@router.post("/important-materials/{material_key}/acknowledge", response_model=DigitalCapOut)
async def acknowledge_important_material(
    material_key: str,
    payload: MaterialAcknowledgeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DigitalCapOut:
    try:
        await award_material_acknowledgement(
            session,
            user,
            material_key=material_key,
            material_version=payload.version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cap = await digital_monthly_cap(session)
    earned = await digital_points_this_month(session, user.id)
    return DigitalCapOut(earned=earned, cap=cap, remaining=max(cap - earned, 0))
