"""Mini App E09: exact-day ERA channel publication approval (fail closed)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.services.daily_public_content_service import (
    MOSCOW,
    _channel_target,
    _publication_digest,
    approve_channel_publication,
    has_channel_publication_approval,
    text_for_day,
)

router = APIRouter(prefix="/admin/channel-approval", tags=["admin-channel-approval"])


async def require_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class ChannelApprovalPreviewOut(BaseModel):
    day: str
    target: str | None
    digest: str
    text: str
    approved: bool
    preview: str


class ChannelApprovalIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ChannelApprovalOut(BaseModel):
    day: str
    target: str
    digest: str
    already: bool


def _preview(text: str) -> str:
    body = text.strip()
    return body[:700] + "…" if len(body) > 700 else body


@router.get("/today", response_model=ChannelApprovalPreviewOut)
async def channel_approval_preview(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ChannelApprovalPreviewOut:
    day = datetime.now(MOSCOW).date().isoformat()
    target = _channel_target(settings)
    content = text_for_day(day, "channel_post")
    digest = _publication_digest(content)
    approved = False
    if target is not None:
        approved = await has_channel_publication_approval(session, day, target, content)
    return ChannelApprovalPreviewOut(
        day=day,
        target=str(target) if target is not None else None,
        digest=digest,
        text=content,
        approved=approved,
        preview=_preview(content),
    )


@router.post("/approve", response_model=ChannelApprovalOut)
async def channel_approval_confirm(
    payload: ChannelApprovalIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ChannelApprovalOut:
    today = datetime.now(MOSCOW).date().isoformat()
    if payload.day != today:
        raise HTTPException(status_code=409, detail="channel_approval_day_mismatch")
    target = _channel_target(settings)
    if target is None:
        raise HTTPException(status_code=409, detail="channel_not_configured")
    content = text_for_day(payload.day, "channel_post")
    digest = _publication_digest(content)
    if digest != payload.digest:
        raise HTTPException(status_code=409, detail="channel_approval_text_changed")
    stored, already = await approve_channel_publication(
        session,
        day=payload.day,
        target=str(target),
        text=content,
        actor_id=admin.id,
    )
    await session.commit()
    return ChannelApprovalOut(
        day=payload.day, target=str(target), digest=stored, already=already
    )
