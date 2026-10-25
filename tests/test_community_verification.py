from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.community_verification_models import (
    CommunityMemberIdentity,
    CommunityVerificationCampaign,
)
from app.database.models import User
from app.services.community_verification_service import (
    complete_due_campaigns,
    deliver_identity,
    start_campaign,
)
from app.utils.constants import ApplicationStatus


class CommunityVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(general_chat_id=-100123)
        self.bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="era_test_bot")),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=501)),
            pin_chat_message=AsyncMock(return_value=True),
        )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_start_is_idempotent_and_posts_group_launch_once(self) -> None:
        async with self.sessions() as session:
            user = User(
                telegram_id=1001,
                first_name="Pending",
                application_status=ApplicationStatus.PENDING,
            )
            session.add(user)
            await session.flush()

            first = await start_campaign(
                self.bot,
                self.settings,
                session,
                duration_hours=48,
                actor_id=None,
                idempotency_key="verification:test",
            )
            second = await start_campaign(
                self.bot,
                self.settings,
                session,
                duration_hours=48,
                actor_id=None,
                idempotency_key="verification:test",
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.campaign.id, second.campaign.id)
            campaigns = int(
                await session.scalar(select(func.count()).select_from(CommunityVerificationCampaign)) or 0
            )
            self.assertEqual(campaigns, 1)
            # One group post + one DM to the known pending participant. The
            # second Start call sends neither again.
            self.assertEqual(self.bot.send_message.await_count, 2)
            self.bot.pin_chat_message.assert_awaited_once()

    async def test_registration_reminder_skips_pending_approved_and_rejected(self) -> None:
        async with self.sessions() as session:
            campaign = CommunityVerificationCampaign(
                launch_key="segmentation",
                status="active",
                duration_hours=48,
                started_at=datetime.now(timezone.utc),
                ends_at=datetime.now(timezone.utc) + timedelta(hours=48),
            )
            session.add(campaign)
            await session.flush()
            for index, status in enumerate(
                [ApplicationStatus.PENDING, ApplicationStatus.APPROVED, ApplicationStatus.REJECTED],
                start=1,
            ):
                user = User(
                    telegram_id=2000 + index,
                    first_name=f"U{index}",
                    application_status=status,
                )
                session.add(user)
                await session.flush()
                identity = CommunityMemberIdentity(
                    telegram_id=user.telegram_id,
                    user_id=user.id,
                    general_chat_id=-100123,
                    first_seen_at=datetime.now(timezone.utc),
                    last_seen_at=datetime.now(timezone.utc),
                    is_current_member=True,
                )
                session.add(identity)
                await session.flush()
                delivery = await deliver_identity(
                    self.bot, session, campaign, identity, kind="reminder"
                )
                self.assertEqual(delivery.status, "skipped")
            self.assertEqual(self.bot.send_message.await_count, 0)

    async def test_unregistered_member_receives_registration_reminder(self) -> None:
        async with self.sessions() as session:
            campaign = CommunityVerificationCampaign(
                launch_key="unregistered",
                status="active",
                duration_hours=24,
                started_at=datetime.now(timezone.utc),
                ends_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
            identity = CommunityMemberIdentity(
                telegram_id=9999,
                user_id=None,
                general_chat_id=-100123,
                first_seen_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
                is_current_member=True,
            )
            session.add_all([campaign, identity])
            await session.flush()
            delivery = await deliver_identity(
                self.bot, session, campaign, identity, kind="reminder"
            )
            self.assertEqual(delivery.status, "sent")
            self.assertEqual(delivery.attempt_count, 1)

    async def test_campaign_expiry_does_not_remove_or_archive_identity(self) -> None:
        async with self.sessions() as session:
            now = datetime.now(timezone.utc)
            campaign = CommunityVerificationCampaign(
                launch_key="expired",
                status="active",
                duration_hours=24,
                started_at=now - timedelta(days=2),
                ends_at=now - timedelta(days=1),
            )
            identity = CommunityMemberIdentity(
                telegram_id=7777,
                user_id=None,
                general_chat_id=-100123,
                first_seen_at=now - timedelta(days=2),
                last_seen_at=now - timedelta(days=1),
                is_current_member=True,
            )
            session.add_all([campaign, identity])
            await session.flush()

            changed = await complete_due_campaigns(session, now=now)

            self.assertEqual(changed, 1)
            self.assertEqual(campaign.status, "completed")
            self.assertTrue(identity.is_current_member)


if __name__ == "__main__":
    unittest.main()
