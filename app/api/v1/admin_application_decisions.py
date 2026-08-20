from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.application_review_service import reject_application
from app.services.authorization_service import is_full_admin
from app.services.chat_access_service import sync_user_chat_access
from app.services.notification_service import safe_send
from app.utils import texts

router = APIRouter(prefix="/admin", tags=["admin-applications"])


class CommentIn(BaseModel):
    comment: str = ""


class ApplicationOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    city: str | None
    occupation: str | None
    motivation: str | None
    application_status: str
    created_at: str


def _out(user: User) -> ApplicationOut:
    return ApplicationOut(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        city=user.city,
        occupation=user.occupation,
        motivation=user.motivation,
        application_status=user.application_status,
        created_at=user.created_at.isoformat(),
    )


def _require_full_admin(user: User, settings: Settings) -> None:
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")


@router.post("/applications/{user_id}/reject", response_model=ApplicationOut)
async def reject_application_with_access_sync(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> ApplicationOut:
    """Canonical Mini App rejection flow.

    The reason is retained in the internal audit/review trail only. The member
    receives the generic rejection state and Chat Access immediately declines
    outstanding join requests/removes an existing rejected member.
    """
    _require_full_admin(admin, settings)
    comment = payload.comment.strip()
    if not comment:
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await reject_application(session, target, actor_id=admin.id, comment=comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)

    if bot is not None:
        # Business rule: rejection reason is internal-only. Do not echo the
        # review comment into Telegram.
        await safe_send(bot, target.telegram_id, texts.APPLICATION_REJECTED)
        await sync_user_chat_access(bot, settings, session, target)
    return _out(target)
