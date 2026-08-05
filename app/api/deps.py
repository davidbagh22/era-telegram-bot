from __future__ import annotations

from collections.abc import AsyncIterator

from aiogram import Bot
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
    """Yields a request-scoped session and commits on a clean exit.

    Without the explicit commit, `async with session_factory()` only ever
    closes the session — SQLAlchemy rolls back anything uncommitted on
    close. Every mutating Mini App endpoint (admin decisions, event
    registration, leader task creation, offer applications, ...) computed
    the right in-memory result and returned 200, but the write never
    reached the database: the next request opened a fresh session that
    never saw it. `app/api/v1/projects.py` had already independently
    worked around this per-endpoint (`_commit_if_possible`); this fixes it
    at the source for every route instead. Found by PR16's E2E suite: a
    seeded pending applicant kept coming back as pending after a real,
    200-OK "approve" call.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_bot(request: Request) -> Bot | None:
    """The same aiogram Bot instance the webhook uses (bot and API share one
    process/deploy — see docs/ERA_PLATFORM_PROGRESS.md). None outside the
    app's lifespan (e.g. in tests), so callers must handle that instead of
    assuming a bot is always available."""
    return getattr(request.app.state, "bot", None)


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
