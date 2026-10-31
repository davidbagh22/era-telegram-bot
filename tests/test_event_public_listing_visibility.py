"""Public event listing is reversible without changing participant records."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.admin_event_create import (
    EventListingPatch, require_event_manager, router, set_event_public_listing,
)
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AuditLog, Event, EventRegistration, User
from app.services.activity_service import list_events
from app.services.event_service import published_events
from app.utils.constants import EventStatus, RegistrationStatus


class PublicListingVisibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _user_event(self, session, status=EventStatus.PUBLISHED):
        user = User(telegram_id=100123, first_name="Test", role="admin")
        session.add(user)
        await session.flush()
        event = Event(
            title="Visibility fixture", description="Test only",
            event_date=date.today() + timedelta(days=2), event_time=time(18, 0),
            location="Test", format="offline", status=status, created_by=user.id,
        )
        session.add(event)
        await session.flush()
        return user, event

    async def test_hidden_event_not_discovered_but_registration_history_survives(self):
        async with self.factory() as session:
            user, hidden = await self._user_event(session)
            visible = Event(
                title="Visible", description="Test", event_date=hidden.event_date,
                event_time=time(19, 0), location="Test", format="offline",
                status=EventStatus.PUBLISHED, created_by=user.id,
            )
            legacy = Event(
                title="Legacy", description="Test", event_date=hidden.event_date,
                event_time=time(20, 0), location="Test", format="offline",
                status=EventStatus.PUBLISHED, created_by=user.id,
            )
            session.add_all([visible, legacy])
            await session.flush()
            session.add_all([
                EventExperience(event_id=hidden.id, show_in_public_listing=False),
                EventExperience(event_id=visible.id, show_in_public_listing=True),
                EventRegistration(event_id=hidden.id, user_id=user.id, status=RegistrationStatus.REGISTERED),
            ])
            await session.flush()
            self.assertEqual({e.id for e in await published_events(session)}, {visible.id, legacy.id})
            self.assertEqual({e.id for e, _ in await list_events(session, user, "all")}, {visible.id, legacy.id})
            self.assertEqual([e.id for e, _ in await list_events(session, user, "mine")], [hidden.id])
            self.assertIsNotNone(await session.scalar(select(EventRegistration).where(
                EventRegistration.event_id == hidden.id, EventRegistration.user_id == user.id)))

    async def test_manager_can_hide_and_restore_without_touching_registration(self):
        async with self.factory() as session:
            user, event = await self._user_event(session)
            session.add(EventRegistration(event_id=event.id, user_id=user.id,
                                          status=RegistrationStatus.REGISTERED))
            await session.flush()
            hidden = await set_event_public_listing(event.id, EventListingPatch(visible=False), user, session)
            self.assertFalse(hidden.show_in_public_listing)
            self.assertEqual(await published_events(session), [])
            self.assertEqual(len(await list_events(session, user, "mine")), 1)
            # Repeating the same request must not create another audit record or
            # alter participation. This is important for mobile retry behavior.
            repeated = await set_event_public_listing(
                event.id, EventListingPatch(visible=False), user, session,
            )
            self.assertFalse(repeated.show_in_public_listing)
            await session.flush()
            hidden_actions = (await session.scalars(select(AuditLog.action).where(
                AuditLog.entity_type == "event", AuditLog.entity_id == event.id))).all()
            self.assertEqual(hidden_actions.count("event.public_listing_visibility_changed"), 1)
            self.assertEqual(event.status, EventStatus.PUBLISHED)
            self.assertIsNotNone(await session.scalar(select(EventRegistration).where(
                EventRegistration.event_id == event.id,
                EventRegistration.user_id == user.id,
            )))
            restored = await set_event_public_listing(event.id, EventListingPatch(visible=True), user, session)
            self.assertTrue(restored.show_in_public_listing)
            self.assertEqual([e.id for e in await published_events(session)], [event.id])
            await session.flush()
            actions = (await session.scalars(select(AuditLog.action).where(
                AuditLog.entity_type == "event", AuditLog.entity_id == event.id))).all()
            self.assertEqual(actions.count("event.public_listing_visibility_changed"), 2)

    async def test_hidden_completed_registration_does_not_reappear_in_general_afisha(self):
        # The general tab historically unions registered completed events so
        # attendance codes remain accessible. A hidden completed event must
        # remain in personal history, not reappear in the public listing.
        async with self.factory() as session:
            user, hidden = await self._user_event(session, EventStatus.COMPLETED)
            visible = Event(
                title="Visible completed", description="Test",
                event_date=hidden.event_date, event_time=time(19, 0),
                location="Test", format="offline", status=EventStatus.COMPLETED,
                created_by=user.id,
            )
            session.add(visible)
            await session.flush()
            session.add_all([
                EventExperience(event_id=hidden.id, show_in_public_listing=False),
                EventExperience(event_id=visible.id, show_in_public_listing=True),
                EventRegistration(event_id=hidden.id, user_id=user.id, status=RegistrationStatus.REGISTERED),
                EventRegistration(event_id=visible.id, user_id=user.id, status=RegistrationStatus.REGISTERED),
            ])
            await session.flush()
            self.assertEqual(
                {event.id for event, _ in await list_events(session, user, "all")},
                {visible.id},
            )
            for scope in ("mine", "past"):
                with self.subTest(scope=scope):
                    self.assertEqual(
                        {event.id for event, _ in await list_events(session, user, scope)},
                        {hidden.id, visible.id},
                    )

    async def test_unpublished_event_rejects_visibility_mutation(self):
        async with self.factory() as session:
            user, event = await self._user_event(session, EventStatus.DRAFT)
            with self.assertRaises(HTTPException) as caught:
                await set_event_public_listing(event.id, EventListingPatch(visible=False), user, session)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertIsNone(await session.get(EventExperience, event.id))

    async def test_listing_route_requires_manager_dependency(self):
        # This protects the HTTP boundary, not merely the helper called by tests.
        route = next(
            item for item in router.routes
            if item.path.endswith("/{event_id}/listing") and "PATCH" in item.methods
        )
        self.assertTrue(any(
            dependency.call is require_event_manager
            for dependency in route.dependant.dependencies
        ))
        with patch("app.api.v1.admin_event_create.can_manage_events", return_value=False) as allowed:
            with self.assertRaises(HTTPException) as denied:
                await require_event_manager(
                    user=SimpleNamespace(telegram_id=100456), settings=SimpleNamespace(),
                )
        self.assertEqual(denied.exception.status_code, 403)
        allowed.assert_called_once()

    async def test_unknown_event_cannot_create_visibility_or_audit_rows(self):
        async with self.factory() as session:
            user, existing = await self._user_event(session)
            unknown_id = existing.id + 1000
            with self.assertRaises(HTTPException) as missing:
                await set_event_public_listing(
                    unknown_id, EventListingPatch(visible=False), user, session,
                )
            self.assertEqual(missing.exception.status_code, 404)
            self.assertIsNone(await session.get(EventExperience, unknown_id))
            self.assertFalse((await session.scalars(select(AuditLog).where(
                AuditLog.entity_type == "event", AuditLog.entity_id == unknown_id,
            ))).all())
