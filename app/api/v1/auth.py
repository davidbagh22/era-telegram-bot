from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_settings
from app.api.security import InitDataError, create_session_token, verify_init_data
from app.api.v1.schemas import MiniAppUserSummary, summarize_user
from app.config import Settings
from app.repositories.users import get_user_by_telegram_id

router = APIRouter(tags=["miniapp-auth"])

SESSION_TTL_SECONDS = 3600


class MiniAppAuthRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    init_data: str = Field(default="", alias="initData")
    dev_telegram_id: int | None = Field(default=None, alias="devTelegramId")


class MiniAppAuthResponse(BaseModel):
    token: str
    expires_at: str
    user: MiniAppUserSummary


@router.post("/miniapp/auth", response_model=MiniAppAuthResponse)
async def authenticate(
    payload: MiniAppAuthRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MiniAppAuthResponse:
    if settings.dev_auth_enabled and payload.dev_telegram_id is not None:
        telegram_id = payload.dev_telegram_id
    else:
        try:
            verified = verify_init_data(
                payload.init_data,
                bot_token=settings.bot_token,
                max_age_seconds=settings.init_data_max_age_seconds,
            )
        except InitDataError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        telegram_id = verified.telegram_id

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_registered")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="user_blocked")
    if user.is_archived:
        raise HTTPException(status_code=403, detail="user_archived")
    if not settings.miniapp_auth_secret:
        raise HTTPException(status_code=500, detail="miniapp_auth_not_configured")

    token, expires_at = create_session_token(
        telegram_id=telegram_id,
        secret=settings.miniapp_auth_secret,
        ttl_seconds=SESSION_TTL_SECONDS,
    )
    return MiniAppAuthResponse(
        token=token,
        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        user=summarize_user(user, settings),
    )
