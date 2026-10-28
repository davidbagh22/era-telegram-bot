"""Regression tests for the legacy unauthenticated event-poster route."""

from __future__ import annotations

import unittest
from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.event_posters import read_public_event_poster
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, User
from app.utils.constants import EventStatus


class PublicEventPosterSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.serial = 0

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _event(self, session, status: EventStatus) -> Event:
        self.serial += 1
        user = User(telegram_id=881_000 + self.serial, first_name="Creator")
        session.add(user)
        await session.flush()
        event = Event(
            title="Private before publication",
            description="Moderation details",
            event_date=date.today() + timedelta(days=5),
            event_time=time(18, 0),
            location="Private location",
            format="offline",
            created_by=user.id,
            status=status,
        )
        session.add(event)
        await session.flush()
        session.add(
            EventExperience(
                event_id=event.id,
                poster_bytes=b"poster-bytes",
                poster_content_type="image/png",
            )
        )
        await session.flush()
        return event

    async def test_public_route_does_not_expose_unpublished_or_historical_statuses(self) -> None:
        async with self.sessions() as session:
            for status in (
                EventStatus.DRAFT,
                EventStatus.PENDING_APPROVAL,
                EventStatus.ACTIVE,
                EventStatus.COMPLETED,
                EventStatus.CANCELLED,
            ):
                with self.subTest(status=status):
                    event = await self._event(session, status)
                    with self.assertRaises(HTTPException) as caught:
                        await read_public_event_poster(event.id, session=session)
                    self.assertEqual(caught.exception.status_code, 404)

            approved = await self._event(session, EventStatus.APPROVED)
            response = await read_public_event_poster(approved.id, session=session)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b"poster-bytes")
            self.assertEqual(response.media_type, "image/png")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_public_route_blocks_executable_or_unknown_mime(self) -> None:
        async with self.sessions() as session:
            event = await self._event(session, EventStatus.PUBLISHED)
            experience = await session.get(EventExperience, event.id)
            for content_type in (
                "text/html",
                "image/svg+xml",
                "application/javascript",
                "application/octet-stream",
            ):
                with self.subTest(content_type=content_type):
                    experience.poster_content_type = content_type
                    await session.flush()
                    with self.assertRaises(HTTPException) as caught:
                        await read_public_event_poster(event.id, session=session)
                    self.assertEqual(caught.exception.status_code, 404)

    async def test_public_route_keeps_safe_mobile_images(self) -> None:
        async with self.sessions() as session:
            event = await self._event(session, EventStatus.PUBLISHED)
            experience = await session.get(EventExperience, event.id)
            for content_type, expected in (
                (" IMAGE/PNG; charset=binary ", "image/png"),
                ("image/heic", "image/heic"),
                ("image/heif", "image/heif"),
                ("image/avif", "image/avif"),
            ):
                with self.subTest(content_type=content_type):
                    experience.poster_content_type = content_type
                    await session.flush()
                    response = await read_public_event_poster(event.id, session=session)
                    self.assertEqual(response.media_type, expected)
                    self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_public_route_unknown_event_returns_404(self) -> None:
        async with self.sessions() as session:
            with self.assertRaises(HTTPException) as caught:
                await read_public_event_poster(999_999, session=session)
            self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
