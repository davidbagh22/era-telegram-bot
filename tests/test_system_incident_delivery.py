from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import User
from app.database.system_models import NotificationDelivery, SystemIncident
from app.services.notification_service import _session_factory
from app.services.system_health_service import (
    HealthCheck,
    _notify_incident_changes,
    _sync_incidents,
)
from app.utils.constants import Role


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.calls.append((chat_id, text))
        return object()


class SystemIncidentDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "system-incidents.db"
        self.database_url = f"sqlite+aiosqlite:///{db_path}"
        self.settings = Settings(
            bot_token="1234567890:test-token",
            database_url=self.database_url,
        )
        self.engine = create_async_engine(self.database_url)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            session.add(
                User(
                    telegram_id=880001,
                    first_name="Admin",
                    role=Role.ADMIN,
                )
            )
            await session.commit()
        self.bot = FakeBot()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        _session_factory.cache_clear()
        self.tmp.cleanup()

    async def _incident(self) -> SystemIncident:
        async with self.factory() as session:
            return await session.scalar(
                select(SystemIncident).where(SystemIncident.dedupe_key == "health:backup")
            )

    async def test_alert_recovery_and_reopen_have_one_delivery_per_episode(self) -> None:
        failing = HealthCheck(
            key="backup",
            title="Резервное копирование",
            status="error",
            severity="high",
            detail="restore verification failed",
        )
        healthy = HealthCheck(
            key="backup",
            title="Резервное копирование",
            status="ok",
            severity="info",
            detail="ok",
        )

        # Episode 1 opens and sends once.
        async with self.factory() as session:
            await _sync_incidents(session, [failing], "commit-one")
            await session.commit()
        await _notify_incident_changes(self.bot, self.settings, self.factory)
        await _notify_incident_changes(self.bot, self.settings, self.factory)
        self.assertEqual(len(self.bot.calls), 1)
        incident = await self._incident()
        self.assertTrue(incident.admin_notified)
        self.assertEqual(incident.notification_generation, 1)

        # Recovery is a separate stable delivery and is also exactly once.
        async with self.factory() as session:
            await _sync_incidents(session, [healthy], "commit-two")
            await session.commit()
        await _notify_incident_changes(self.bot, self.settings, self.factory)
        await _notify_incident_changes(self.bot, self.settings, self.factory)
        self.assertEqual(len(self.bot.calls), 2)
        incident = await self._incident()
        self.assertEqual(incident.status, "resolved")
        self.assertTrue(incident.recovery_notified)

        # Same dedupe_key failing again is a new episode, not a suppressed old
        # alert. Generation increments once and the new alert is sent once.
        async with self.factory() as session:
            await _sync_incidents(session, [failing], "commit-three")
            await session.commit()
        incident = await self._incident()
        self.assertEqual(incident.status, "open")
        self.assertEqual(incident.notification_generation, 2)
        self.assertFalse(incident.admin_notified)

        await _notify_incident_changes(self.bot, self.settings, self.factory)
        await _notify_incident_changes(self.bot, self.settings, self.factory)
        self.assertEqual(len(self.bot.calls), 3)

        async with self.factory() as session:
            deliveries = list(
                (
                    await session.scalars(
                        select(NotificationDelivery).order_by(NotificationDelivery.id)
                    )
                ).all()
            )
        self.assertEqual(len(deliveries), 3)
        self.assertEqual({row.status for row in deliveries}, {"sent"})
        self.assertEqual(
            {row.notification_type for row in deliveries},
            {"system_incident", "system_incident_recovery"},
        )

    async def test_unfinished_alert_is_not_marked_delivered_without_recipient(self) -> None:
        no_admin_settings = Settings(
            bot_token="1234567890:test-token",
            database_url=self.database_url,
        )
        async with self.factory() as session:
            admin = await session.scalar(select(User).where(User.role == Role.ADMIN))
            admin.role = Role.PARTICIPANT
            now = datetime.now(timezone.utc)
            session.add(
                SystemIncident(
                    dedupe_key="health:no-recipient",
                    category="runtime_health",
                    severity="high",
                    status="open",
                    title="No recipient",
                    detail="test",
                    check_key="no-recipient",
                    first_seen_at=now,
                    last_seen_at=now,
                    current_commit="x",
                    notification_generation=1,
                    admin_notified=False,
                )
            )
            await session.commit()

        await _notify_incident_changes(self.bot, no_admin_settings, self.factory)
        async with self.factory() as session:
            incident = await session.scalar(
                select(SystemIncident).where(
                    SystemIncident.dedupe_key == "health:no-recipient"
                )
            )
            self.assertFalse(incident.admin_notified)
        self.assertEqual(self.bot.calls, [])


if __name__ == "__main__":
    unittest.main()
