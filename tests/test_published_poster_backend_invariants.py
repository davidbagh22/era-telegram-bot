"""Published-poster edits are image-only and never republish or mutate attendance.

Disposable SQLite fixtures only. No Telegram calls or production writes.
"""
from __future__ import annotations

import io
import unittest
from datetime import date, time, timedelta
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.datastructures import Headers, UploadFile

from app.api.v1.admin_event_create import (
    read_admin_event_poster_preview,
    remove_event_poster,
    upload_event_poster,
)
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.utils.constants import EventStatus, RegistrationStatus


PNG = b"\x89PNG\r\n\x1a\n" + b"test-fixture"


def upload(data: bytes, mime: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="poster.png",
        headers=Headers({"content-type": mime}),
    )


class PublishedPosterBackendInvariants(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def fixture(self, session):
        admin = User(telegram_id=801001, first_name="Editor", role="admin")
        participant = User(telegram_id=801002, first_name="Participant")
        session.add_all([admin, participant])
        await session.flush()
        event = Event(
            title="Existing published event", description="Original description",
            event_date=date.today() + timedelta(days=7), event_time=time(18, 0),
            location="Test", format="offline", status=EventStatus.PUBLISHED,
            created_by=admin.id, points_for_visit=50,
        )
        session.add(event)
        await session.flush()
        experience = EventExperience(
            event_id=event.id, poster_bytes=PNG, poster_content_type="image/png",
            announcement_status="sent",
        )
        registration = EventRegistration(
            event_id=event.id, user_id=participant.id,
            status=RegistrationStatus.REGISTERED,
        )
        session.add_all([experience, registration])
        await session.flush()
        return admin, event, experience, registration

    async def test_replace_and_remove_preserve_event_registration_and_delivery_state(self):
        async with self.sessions() as session:
            admin, event, experience, registration = await self.fixture(session)
            with patch(
                "app.api.v1.admin_event_create._notify_changed_event",
                new_callable=AsyncMock,
            ) as notify:
                replaced = await upload_event_poster(
                    event.id, upload(PNG + b"new"), admin, session,
                )
                self.assertTrue(replaced.has_poster)
                self.assertEqual(experience.poster_bytes, PNG + b"new")
                preview = await read_admin_event_poster_preview(event.id, admin, session)
                self.assertEqual(preview.body, PNG + b"new")
                self.assertEqual(preview.headers["cache-control"], "private, no-store")
                self.assertEqual(preview.headers["x-content-type-options"], "nosniff")

                removed = await remove_event_poster(event.id, admin, session)
                self.assertFalse(removed.has_poster)
                self.assertIsNone(experience.poster_bytes)
                self.assertIsNone(experience.poster_content_type)
                notify.assert_not_awaited()

            self.assertEqual(event.status, EventStatus.PUBLISHED)
            self.assertEqual(event.points_for_visit, 50)
            self.assertEqual(experience.announcement_status, "sent")
            self.assertEqual(
                (await session.scalar(select(EventRegistration).where(
                    EventRegistration.event_id == event.id,
                    EventRegistration.user_id == registration.user_id,
                ))).status,
                RegistrationStatus.REGISTERED,
            )

    async def test_invalid_image_does_not_replace_existing_poster(self):
        async with self.sessions() as session:
            admin, event, experience, _ = await self.fixture(session)
            for data, mime, status in [
                (b"not an image", "image/png", 422),
                (PNG, "text/html", 422),
                (PNG + b"x" * (5 * 1024 * 1024), "image/png", 413),
            ]:
                with self.subTest(mime=mime, status=status):
                    with self.assertRaises(HTTPException) as caught:
                        await upload_event_poster(event.id, upload(data, mime), admin, session)
                    self.assertEqual(caught.exception.status_code, status)
                    self.assertEqual(experience.poster_bytes, PNG)
                    self.assertEqual(experience.announcement_status, "sent")

    async def test_preview_rejects_unsafe_legacy_mime(self):
        async with self.sessions() as session:
            admin, event, experience, _ = await self.fixture(session)
            experience.poster_content_type = "text/html"
            with self.assertRaises(HTTPException) as caught:
                await read_admin_event_poster_preview(event.id, admin, session)
            self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
