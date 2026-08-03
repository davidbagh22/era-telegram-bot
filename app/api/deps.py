from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import SessionTokenError, decode_session_token
from app.config import Settings
from app.config import get_settings as get_app_settings
from app.database.models import User
from app.repositories.users import get_user_by_telegram_id


def get_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_app_settings()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_session_token(token, settings.miniapp_auth_secret)
    except SessionTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = await get_user_by_telegram_id(session, payload.telegram_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user_not_found")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="user_blocked")
    if user.is_archived:
        raise HTTPException(status_code=403, detail="user_archived")
    return user
