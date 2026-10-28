"""Unpublished Mini App event details and poster must remain private."""
from __future__ import annotations

import unittest
from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.events import read_event, read_event_poster
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, User
from app.utils.constants import EventStatus


class EventVisibilityApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _make_event(self, session, status):
        user = User(telegram_id=777_000 + len(session.new), first_name="Viewer")
        session.add(user)
        await session.flush()
        event = Event(
            title="Unpublished review material",
            description="Private moderation content",
            event_date=date.today() + timedelta(days=5),
            event_time=time(18, 0),
            location="Private location",
            format="offline",
            created_by=user.id,
            status=status,
        )
        session.add(event)
        await session.flush()
        session.add(EventExperience(
            event_id=event.id,
            poster_bytes=b"private-poster-bytes",
            poster_content_type="image/png",
        ))
        await session.flush()
        return user, event

    async def test_draft_and_pending_details_are_not_public(self):
        for status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL):
            with self.subTest(status=status):
                async with self.sessions() as session:
                    viewer, event = await self._make_event(session, status)
                    with self.assertRaises(HTTPException) as caught:
                        await read_event(event.id, user=viewer, session=session)
                    self.assertEqual(caught.exception.status_code, 404)

    async def test_draft_and_pending_posters_are_not_public(self):
        for status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL):
            with self.subTest(status=status):
                async with self.sessions() as session:
                    viewer, event = await self._make_event(session, status)
                    with self.assertRaises(HTTPException) as caught:
                        await read_event_poster(event.id, _user=viewer, session=session)
                    self.assertEqual(caught.exception.status_code, 404)
                    self.assertEqual(caught.exception.detail, "event_poster_not_found")

    async def test_approved_event_poster_remains_available(self):
        async with self.sessions() as session:
            viewer, event = await self._make_event(session, EventStatus.APPROVED)
            response = await read_event_poster(event.id, _user=viewer, session=session)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b"private-poster-bytes")
            self.assertEqual(response.media_type, "image/png")
            self.assertEqual(response.headers["cache-control"], "private, max-age=300")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_active_content_types_are_not_served_under_miniapp_origin(self):
        async with self.sessions() as session:
            viewer, event = await self._make_event(session, EventStatus.APPROVED)
            experience = await session.get(EventExperience, event.id)
            for unsafe_type in ("text/html", "image/svg+xml", "application/javascript"):
                with self.subTest(content_type=unsafe_type):
                    experience.poster_content_type = unsafe_type
                    await session.flush()
                    with self.assertRaises(HTTPException) as caught:
                        await read_event_poster(event.id, _user=viewer, session=session)
                    self.assertEqual(caught.exception.status_code, 404)

    async def test_normalized_safe_image_content_type_is_allowed(self):
        async with self.sessions() as session:
            viewer, event = await self._make_event(session, EventStatus.APPROVED)
            experience = await session.get(EventExperience, event.id)
            experience.poster_content_type = " IMAGE/PNG; charset=binary "
            await session.flush()
            for safe_type, expected in (
                (" IMAGE/PNG; charset=binary ", "image/png"),
                ("image/heic", "image/heic"),
                ("image/heif", "image/heif"),
                ("image/avif", "image/avif"),
            ):
                with self.subTest(content_type=safe_type):
                    experience.poster_content_type = safe_type
                    await session.flush()
                    response = await read_event_poster(event.id, _user=viewer, session=session)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.media_type, expected)
                    self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_unknown_poster_is_not_found(self):
        async with self.sessions() as session:
            viewer = User(telegram_id=779_000, first_name="Viewer")
            session.add(viewer)
            await session.flush()
            with self.assertRaises(HTTPException) as caught:
                await read_event_poster(999999, _user=viewer, session=session)
            self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
