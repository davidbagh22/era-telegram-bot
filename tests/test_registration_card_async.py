"""A freshly INSERTed User must yield a rich card, without implicit async IO."""
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.database.base import Base
from app.database.models import User
from app.services.admin_user_card import build_admin_user_card
from app.utils.constants import ApplicationStatus, Role


def test_new_registration_and_expired_card_relationships() -> None:
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                user = User(telegram_id=440001, first_name="Նոր", last_name="Участник",
                            role=Role.PARTICIPANT, application_status=ApplicationStatus.PENDING)
                session.add(user)
                await session.commit()
                card = await build_admin_user_card(session, user, mode="application")
                assert "Նոր Участник" in card.text
                assert "Права: нет отдельных прав" in card.text
                assert "admin:approve_user:" in str(card.reply_markup)
                session.expire(user, ["departments", "directions", "permission_grants", "created_at"])
                profile = await build_admin_user_card(session, user)
                assert "Направления: не выбраны" in profile.text
        finally:
            await engine.dispose()
    asyncio.run(scenario())
