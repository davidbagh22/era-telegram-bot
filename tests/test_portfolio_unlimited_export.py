"""PDF/export path must not silently truncate long ERA activity lists."""

from __future__ import annotations

import unittest
from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, EventRegistration, User
from app.services.portfolio_service import build_portfolio_data
from app.utils.constants import EventStatus, RegistrationStatus


class PortfolioUnlimitedExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_full_export_keeps_more_than_preview_limit(self) -> None:
        async with self.session_factory() as session:
            user = User(
                telegram_id=4242,
                first_name="Export",
                phone="+10000000042",
                city="Yerevan",
                education_work="Study",
                occupation="Student",
                motivation="Grow",
                available_time="Evenings",
                desired_path="participant",
                personal_data_consent=True,
                is_channel_subscribed=True,
                role="participant",
            )
            session.add(user)
            await session.flush()
            for index in range(15):
                event = Event(
                    title=f"Event {index}",
                    description="d",
                    event_date=date.today() - timedelta(days=index + 1),
                    event_time=time(18, 0),
                    location="Yerevan",
                    format="offline",
                    status=EventStatus.COMPLETED,
                    created_by=user.id,
                )
                session.add(event)
                await session.flush()
                session.add(
                    EventRegistration(
                        event_id=event.id,
                        user_id=user.id,
                        status=RegistrationStatus.ATTENDED,
                    )
                )
            await session.flush()

            preview = await build_portfolio_data(session, user)
            full = await build_portfolio_data(session, user, preview_limit=None)
            self.assertEqual(len(preview.events), 12)
            self.assertEqual(len(full.events), 15)


if __name__ == "__main__":
    unittest.main()
