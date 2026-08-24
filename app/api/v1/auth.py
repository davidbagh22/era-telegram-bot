from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.api.security import InitDataError, create_session_token, verify_init_data
from app.api.v1.schemas import MiniAppUserSummary, summarize_user
from app.config import Settings
from app.repositories.users import get_user_by_telegram_id

logger = logging.getLogger(__name__)

# Generous enough for a user re-opening the Mini App repeatedly across
# several tabs/devices behind one IP (offices/NATs share one outbound
# address), tight enough to blunt a scripted attempt to mint sessions for
# many Telegram IDs. Was 20 — raised after the real cause of the
# intermittent rewards.spec.ts/surveys.spec.ts CI failures turned out to
# be this exact limit: the whole E2E suite runs single-worker, sequential,
# and every spec's page load(s) POST here, all from the CI runner's one
# IP, well within one 60s window — 20 was already only a few specs deep
# into a full ~24-file run. Confirmed via uvicorn.log on the failing CI
# runs (`429 Too Many Requests` on this exact endpoint, at this exact
# position in the run, reproducing identically on main before this fix).
AUTH_RATE_LIMIT = 60
AUTH_RATE_LIMIT_WINDOW_SECONDS = 60

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
    request: Request,
    payload: MiniAppAuthRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MiniAppAuthResponse:
    # Production auth keeps the shared-IP bucket exactly as before. Dev auth
    # is forbidden by deployment safety checks, so only local/E2E sessions
    # get per-fixture buckets; this prevents unrelated Playwright users from
    # exhausting one another's allowance without weakening production.
    dev_auth = settings.dev_auth_enabled and payload.dev_telegram_id is not None
    rate_limit_prefix = (
        f"miniapp_auth_dev_{payload.dev_telegram_id}" if dev_auth else "miniapp_auth"
    )
    await enforce_rate_limit(
        request,
        key_prefix=rate_limit_prefix,
        limit=AUTH_RATE_LIMIT,
        window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    if dev_auth:
        telegram_id = payload.dev_telegram_id
    else:
        try:
            verified = verify_init_data(
                payload.init_data,
                bot_token=settings.bot_token,
                max_age_seconds=settings.init_data_max_age_seconds,
            )
        except InitDataError as exc:
            # No server-side trace of *why* an auth attempt failed existed
            # before this — every failure was silently swallowed into a
            # generic "session expired" screen client-side (see
            # frontend/src/screens/AuthErrorScreen.tsx), with nothing to
            # tell a real, uniform failure (e.g. a stray character in
            # BOT_TOKEN corrupting every HMAC check — see
            # strip_secret_whitespace in app/config.py) apart from a user
            # simply not opening the Mini App in time. Never logs the raw
            # init_data itself — it's the one field here that's genuinely
            # sensitive (contains the user's Telegram profile).
            logger.warning("miniapp auth rejected: %s", exc)
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
