from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.repositories.users import get_user_by_telegram_id
from app.services.telegram_auth_service import TelegramIdentity, validate_init_data


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_telegram_identity(
    request: Request,
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    dev_telegram_id: int | None = Header(default=None, alias="X-Dev-Telegram-Id"),
) -> TelegramIdentity:
    settings = request.app.state.settings
    if init_data:
        try:
            return validate_init_data(
                init_data,
                settings.bot_token,
                max_age_seconds=settings.init_data_max_age_seconds,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Не удалось подтвердить вход через Telegram.",
            ) from exc

    if settings.dev_auth_enabled and dev_telegram_id:
        return TelegramIdentity(
            telegram_id=dev_telegram_id,
            username="era_demo",
            first_name="Давид",
            last_name="Багдасарян",
            language_code="ru",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Откройте приложение из Telegram.",
    )


async def get_optional_user(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    return await get_user_by_telegram_id(session, identity.telegram_id)


async def get_current_user(
    user: User | None = Depends(get_optional_user),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Сначала завершите регистрацию.",
        )
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к системе ограничен.",
        )
    if user.application_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Анкета ещё находится на рассмотрении.",
        )
    return user
