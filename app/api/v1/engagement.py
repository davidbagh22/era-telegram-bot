from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services.audit_service import audit
from app.services.digital_engagement_service import (
    award_material_acknowledgement,
    configured_important_materials,
    digital_monthly_cap,
    digital_points_this_month,
)

router = APIRouter(prefix="/engagement", tags=["engagement"])

_PRODUCT_EVENT_RE = re.compile(r"^[a-z0-9_.-]{1,64}$")
_ALLOWED_PRODUCT_METADATA = {"screen", "source", "section", "state", "action"}


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


class ProductEventIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _safe_product_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in metadata.items():
        if key not in _ALLOWED_PRODUCT_METADATA:
            continue
        if value is None:
            continue
        safe[key] = str(value)[:120]
    return safe


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


@router.post("/product-event", status_code=status.HTTP_204_NO_CONTENT)
async def record_product_event(
    payload: ProductEventIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Store low-risk product analytics in the existing audit ledger.

    Only an allow-listed set of short metadata fields is persisted. Free-form
    text, questionnaire answers, phone/email data and other PII are deliberately
    discarded at the API boundary.
    """
    name = payload.name.strip().lower()
    if not _PRODUCT_EVENT_RE.fullmatch(name):
        raise HTTPException(status_code=422, detail="invalid_product_event")
    await audit(
        session,
        actor_id=user.id,
        action=f"product.{name}",
        entity_type="product_event",
        new_value=_safe_product_metadata(payload.metadata),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
