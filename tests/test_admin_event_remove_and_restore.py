"""Admin-only reversible event removal («Убрать» / «Вернуть») tests.

Covers server-side admin-only authorization (denying anonymous, participant,
leader, and non-admin events.manage grantees), soft cancellation via
POST /api/v1/admin/events/{id}/cancel, AuditLog previous-status storage,
POST /api/v1/admin/events/{id}/restore undo, hiding from admin and public
feeds, and preservation of registrations, points, attendance, and certificates.
All notification transport is mocked — no real Telegram messages are sent.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.admin_event_create import (
    EventDraftPatch,
    cancel_event,
    create_event_draft,
    publish_event,
    require_full_admin,
    restore_event,
    router as admin_event_router,
    save_event_draft_step,
)
from app.config import Settings
from app.database.base import Base
from app.database.certificate_models import CertificateIssue
from app.database.models import (
    AttendanceProof,
    AuditLog,
    Event,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    User,
)
from app.services.activity_service import list_events
from app.services.event_registration_service import list_operational_events
from app.utils.constants import EventStatus, RegistrationStatus


def _actor(*, role: str = "participant", grants=(), user_id: int = 24, telegram_id: int = 900024):
    return SimpleNamespace(
        id=user_id,
        telegram_id=telegram_id,
        role=role,
        is_blocked=False,
        is_archived=False,
        permission_grants=list(grants),
    )


def _asgi_client(user):
    app = FastAPI()
    app.include_router(admin_event_router, prefix="/api/v1")
    session = SimpleNamespace(
        get=AsyncMock(side_effect=AssertionError("unauthorized DB read")),
        scalar=AsyncMock(side_effect=AssertionError("unauthorized DB read")),
    )

    async def session_override():
        yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token="1234567890:LOCALTEST",
        general_chat_id=-100,
    )
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), session


class AdminEventRemoveAuthorizationTests(unittest.TestCase):
    def _assert_denied(self, user, expected_status: int):
        client, session = _asgi_client(user)
        with client:
            for path in ("/api/v1/admin/events/7/cancel", "/api/v1/admin/events/7/restore"):
                with self.subTest(path=path, status=expected_status):
                    response = client.post(path)
                    self.assertEqual(response.status_code, expected_status)
                    if expected_status == 403:
                        self.assertEqual(response.json().get("detail"), "admin_access_required")
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()

    def test_anonymous_cannot_cancel_or_restore(self):
        self._assert_denied(None, 401)

    def test_participant_cannot_cancel_or_restore(self):
        self._assert_denied(_actor(role="participant"), 403)

    def test_leader_cannot_cancel_or_restore(self):
        self._assert_denied(_actor(role="leader"), 403)

    def test_global_events_manage_non_admin_cannot_cancel_or_restore(self):
        grant = SimpleNamespace(
            permission="events.manage",
            is_active=True,
            scope_type="global",
            scope_id=0,
        )
        self._assert_denied(_actor(role="leader", grants=(grant,)), 403)

    def test_routes_bind_require_full_admin_dependency(self):
        by_path = {
            route.path: route
            for route in admin_event_router.routes
            if getattr(route, "path", None)
        }
        for suffix in ("/admin/events/{event_id}/cancel", "/admin/events/{event_id}/restore"):
            route = by_path[suffix]
            deps = [dep.call for dep in route.dependant.dependencies]
            self.assertIn(require_full_admin, deps)


class AdminEventRemoveAndRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            bot_token="1234567890:LOCALTEST",
            bot_username="ERA_1bot",
            general_chat_id=-100123,
        )
        async with self.sessions() as session:
            admin = User(
                telegram_id=1001,
                first_name="Admin",
                phone="+37400000001",
                personal_data_consent=True,
                is_channel_subscribed=True,
                role="admin",
                application_status="approved",
            )
            participant = User(
                telegram_id=1002,
                first_name="Participant",
                phone="+37400000002",
                personal_data_consent=True,
                is_channel_subscribed=True,
                role="participant",
                application_status="approved",
            )
            session.add_all([admin, participant])
            await session.commit()
            self.admin = admin
            self.participant = participant

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _create_published_event(
        self,
        *,
        title: str = "Встреча ЭРА",
        event_date: date | None = None,
        status_override: EventStatus | None = None,
    ) -> int:
        target_date = event_date or (date.today() + timedelta(days=5))
        async with self.sessions() as session:
            draft = await create_event_draft(self.admin, session)
            await session.commit()
        async with self.sessions() as session:
            await save_event_draft_step(
                draft.id,
                EventDraftPatch(
                    title=title,
                    short_description="Короткое описание события",
                    location="Дом Москвы",
                    event_date=target_date,
                    event_time=time(18, 0),
                    points_for_visit=50,
                ),
                self.admin,
                session,
                self.settings,
                None,
            )
            await session.commit()
        async with self.sessions() as session:
            await publish_event(draft.id, self.admin, session, self.settings, None)
        if status_override is not None:
            async with self.sessions() as session:
                ev = await session.get(Event, draft.id)
                ev.status = status_override
                await session.commit()
        return draft.id

    async def test_remove_and_restore_preserves_records_audits_status_and_updates_feeds(self):
        event_id = await self._create_published_event(title="Юбилейная встреча ЭРА")

        # Seed registrations, points, attendance proof, and issued certificate.
        async with self.sessions() as session:
            reg = EventRegistration(
                event_id=event_id,
                user_id=self.participant.id,
                status=RegistrationStatus.REGISTERED,
            )
            tx = PointTransaction(
                user_id=self.participant.id,
                points=50,
                reason="Посещение события",
                related_event_id=event_id,
                approved_by=self.admin.id,
            )
            proof = AttendanceProof(
                user_id=self.participant.id,
                event_id=event_id,
                photo_file_id="file_test_123",
                status="approved",
            )
            portfolio = PortfolioItem(
                user_id=self.participant.id,
                item_type="certificate",
                related_event_id=event_id,
                title="Сертификат участника",
                status="verified",
            )
            session.add_all([reg, tx, proof, portfolio])
            await session.flush()
            cert = CertificateIssue(
                user_id=self.participant.id,
                event_id=event_id,
                portfolio_item_id=portfolio.id,
                basis_key=f"event:{event_id}:user:{self.participant.id}",
                revision=1,
                request_key=f"req-{event_id}-{self.participant.id}",
                status="issued",
                snapshot={"title": "Юбилейная встреча ЭРА"},
                issued_by=self.admin.id,
                issued_at=datetime.now(timezone.utc),
            )
            session.add(cert)
            await session.commit()
            reg_id, tx_id, proof_id, cert_id = reg.id, tx.id, proof.id, cert.id

        # Visible in both admin operational list and participant public/mine feeds before removal.
        async with self.sessions() as session:
            admin_ids = [ev.id for ev in await list_operational_events(session)]
            public_ids = [ev.id for ev, _ in await list_events(session, self.participant, "all")]
            mine_ids = [ev.id for ev, _ in await list_events(session, self.participant, "mine")]
            self.assertIn(event_id, admin_ids)
            self.assertIn(event_id, public_ids)
            self.assertIn(event_id, mine_ids)

        # Remove via cancel_event with mocked notification transport.
        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()) as notify_mock:
            async with self.sessions() as session:
                cancelled = await cancel_event(event_id, self.admin, session, self.settings, object())
            self.assertEqual(cancelled.status, EventStatus.CANCELLED)
            notify_mock.assert_awaited_once()
            self.assertEqual(notify_mock.await_args.args[4], ["Мероприятие отменено"])

        # Removed from admin list and public/mine feeds; audit log stores previous status; related records untouched.
        async with self.sessions() as session:
            admin_ids = [ev.id for ev in await list_operational_events(session)]
            public_ids = [ev.id for ev, _ in await list_events(session, self.participant, "all")]
            mine_ids = [ev.id for ev, _ in await list_events(session, self.participant, "mine")]
            self.assertNotIn(event_id, admin_ids)
            self.assertNotIn(event_id, public_ids)
            self.assertNotIn(event_id, mine_ids)

            cancel_audit = await session.scalar(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "event",
                    AuditLog.entity_id == event_id,
                    AuditLog.action == "event.cancelled",
                )
                .order_by(AuditLog.id.desc())
            )
            self.assertIsNotNone(cancel_audit)
            self.assertEqual(cancel_audit.actor_id, self.admin.id)
            self.assertEqual(cancel_audit.old_value["status"], EventStatus.REGISTRATION_OPEN.value)
            self.assertEqual(cancel_audit.new_value["status"], EventStatus.CANCELLED.value)

            self.assertIsNotNone(await session.get(EventRegistration, reg_id))
            self.assertEqual((await session.get(PointTransaction, tx_id)).points, 50)
            self.assertEqual((await session.get(AttendanceProof, proof_id)).status, "approved")
            self.assertEqual((await session.get(CertificateIssue, cert_id)).status, "issued")

        # Undo via restore_event restores exact previous status, re-exposes the event, and sends a restoration notice.
        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()) as restore_notify_mock:
            async with self.sessions() as session:
                restored = await restore_event(event_id, self.admin, session, self.settings, object())
            self.assertEqual(restored.status, EventStatus.REGISTRATION_OPEN)
            restore_notify_mock.assert_awaited_once()
            self.assertEqual(restore_notify_mock.await_args.args[4], ["Мероприятие восстановлено"])

        async with self.sessions() as session:
            admin_ids = [ev.id for ev in await list_operational_events(session)]
            public_ids = [ev.id for ev, _ in await list_events(session, self.participant, "all")]
            self.assertIn(event_id, admin_ids)
            self.assertIn(event_id, public_ids)

            restore_audit = await session.scalar(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "event",
                    AuditLog.entity_id == event_id,
                    AuditLog.action == "event.restored",
                )
                .order_by(AuditLog.id.desc())
            )
            self.assertIsNotNone(restore_audit)
            self.assertEqual(restore_audit.old_value["status"], EventStatus.CANCELLED.value)
            self.assertEqual(restore_audit.new_value["status"], EventStatus.REGISTRATION_OPEN.value)

            # Second restore fails with 409 because event is no longer cancelled.
            with self.assertRaises(HTTPException) as ctx:
                await restore_event(event_id, self.admin, session, self.settings, None)
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "event_not_cancelled")

    async def test_restore_returns_exact_pre_cancel_status_such_as_registration_closed(self):
        event_id = await self._create_published_event(
            title="Закрытая регистрация",
            status_override=EventStatus.REGISTRATION_CLOSED,
        )
        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()):
            async with self.sessions() as session:
                await cancel_event(event_id, self.admin, session, self.settings, object())
        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()) as restore_notify_mock:
            async with self.sessions() as session:
                restored = await restore_event(event_id, self.admin, session, self.settings, object())
            self.assertEqual(restored.status, EventStatus.REGISTRATION_CLOSED)
            restore_notify_mock.assert_awaited_once()
            self.assertEqual(restore_notify_mock.await_args.args[4], ["Мероприятие восстановлено"])

    async def test_completed_event_cancel_skips_cancellation_notice_and_restores_completed(self):
        event_id = await self._create_published_event(
            title="Прошедшая встреча",
            status_override=EventStatus.COMPLETED,
        )
        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()) as notify_mock:
            async with self.sessions() as session:
                cancelled = await cancel_event(event_id, self.admin, session, self.settings, object())
            self.assertEqual(cancelled.status, EventStatus.CANCELLED)
            notify_mock.assert_not_awaited()

        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()) as restore_notify_mock:
            async with self.sessions() as session:
                restored = await restore_event(event_id, self.admin, session, self.settings, object())
            self.assertEqual(restored.status, EventStatus.COMPLETED)
            restore_notify_mock.assert_not_awaited()

    async def test_restore_falls_back_cleanly_when_no_prior_audit_snapshot(self):
        event_id = await self._create_published_event(title="Архивное событие")
        async with self.sessions() as session:
            ev = await session.get(Event, event_id)
            ev.status = EventStatus.CANCELLED
            await session.commit()
        with patch("app.api.v1.admin_event_create._notify_changed_event", new=AsyncMock()) as restore_notify_mock:
            async with self.sessions() as session:
                restored = await restore_event(event_id, self.admin, session, self.settings, object())
            self.assertEqual(restored.status, EventStatus.REGISTRATION_OPEN)
            restore_notify_mock.assert_awaited_once()
            self.assertEqual(restore_notify_mock.await_args.args[4], ["Мероприятие восстановлено"])


if __name__ == "__main__":
    unittest.main()
