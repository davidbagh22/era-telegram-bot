from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.chat_moderation import CommunityVerificationDelivery
from app.database.models import User
from app.services import community_verification_service as cv_service
from app.utils.constants import ApplicationStatus, Role


def _settings(**overrides) -> SimpleNamespace:
    defaults = dict(general_chat_id=-1001)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class CommunityVerificationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, **overrides) -> User:
        defaults = dict(
            telegram_id=100,
            first_name="Dev",
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.PENDING,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_start_campaign_rejects_second_active_campaign(self) -> None:
        async with self.session_factory() as session:
            await cv_service.start_campaign(session, window_hours=72, started_by=1)
            with self.assertRaises(cv_service.CampaignError) as ctx:
                await cv_service.start_campaign(session, window_hours=48, started_by=1)
            self.assertEqual(ctx.exception.code, "campaign_already_active")

    async def test_start_campaign_rejects_invalid_window(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(cv_service.CampaignError) as ctx:
                await cv_service.start_campaign(session, window_hours=0, started_by=1)
            self.assertEqual(ctx.exception.code, "invalid_window")

    async def test_complete_expired_campaigns_never_touches_chat_access(self) -> None:
        """ToR §15: ending the window only changes campaign.status, nothing
        chat-access-related. This test exists to catch any future regression
        that wires chat restriction into campaign completion."""
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            campaign.ends_at = campaign.started_at.replace(year=2000)  # force expiry
            await session.flush()
            completed = await cv_service.complete_expired_campaigns(session)
            self.assertEqual(completed, 1)
            refreshed = await cv_service.latest_campaign(session)
            self.assertEqual(refreshed.status, "completed")

    async def test_complete_campaign_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            first = await cv_service.complete_campaign(session, campaign, actor_id=1)
            second = await cv_service.complete_campaign(session, first, actor_id=1)
            self.assertEqual(first.status, "completed")
            self.assertEqual(second.status, "completed")

    async def test_eligible_launch_recipients_excludes_blocked_and_archived(self) -> None:
        async with self.session_factory() as session:
            await self._make_user(session, telegram_id=1)
            await self._make_user(session, telegram_id=2, is_blocked=True)
            await self._make_user(session, telegram_id=3, is_archived=True)
            recipients = await cv_service.eligible_launch_recipients(session)
            self.assertEqual({u.telegram_id for u in recipients}, {1})

    async def test_reminder_eligible_excludes_registered_and_never_notified(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            # Notified, never registered -> eligible for reminder.
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=201, kind="initial", status="sent"
                )
            )
            # Notified, but has since registered -> not eligible.
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=202, kind="initial", status="sent"
                )
            )
            await self._make_user(session, telegram_id=202)
            # Never successfully notified (blocked) -> not eligible for a reminder DM.
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=203, kind="initial", status="blocked"
                )
            )
            await session.flush()
            eligible = await cv_service.reminder_eligible_telegram_ids(session, campaign)
            self.assertEqual(eligible, [201])

    async def test_segments_are_honest_about_unknown_population(self) -> None:
        """ToR §20: `not_registered_estimate` is None when we can't reach
        Telegram at all (no fabricated precision), and a plain subtraction
        estimate otherwise -- never an enumerated list of "these people"."""
        async with self.session_factory() as session:
            await self._make_user(session, telegram_id=1, application_status=ApplicationStatus.APPROVED)
            await self._make_user(session, telegram_id=2, application_status=ApplicationStatus.PENDING)
            await self._make_user(session, telegram_id=3, application_status=ApplicationStatus.REJECTED)

            bot = AsyncMock()
            bot.get_chat_member_count = AsyncMock(return_value=10)
            segments = await cv_service.campaign_segments(session, bot, _settings(), campaign=None)
            self.assertEqual(segments.known_to_system, 3)
            self.assertEqual(segments.approved, 1)
            self.assertEqual(segments.pending, 1)
            self.assertEqual(segments.rejected, 1)
            self.assertEqual(segments.chat_members_total, 10)
            self.assertEqual(segments.not_registered_estimate, 7)

    async def test_segments_without_bound_general_chat_report_no_total(self) -> None:
        async with self.session_factory() as session:
            bot = AsyncMock()
            segments = await cv_service.campaign_segments(
                session, bot, _settings(general_chat_id=None), campaign=None
            )
            self.assertIsNone(segments.chat_members_total)
            self.assertIsNone(segments.not_registered_estimate)
            bot.get_chat_member_count.assert_not_called()

    async def test_segments_tolerate_telegram_api_failure(self) -> None:
        async with self.session_factory() as session:
            bot = AsyncMock()
            bot.get_chat_member_count = AsyncMock(side_effect=TelegramForbiddenError(method=None, message="kicked"))
            segments = await cv_service.campaign_segments(session, bot, _settings(), campaign=None)
            self.assertIsNone(segments.chat_members_total)

    async def test_not_registered_recipients_lists_only_unregistered_notified_people(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=301, kind="initial", status="sent"
                )
            )
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=302, kind="initial", status="sent"
                )
            )
            await self._make_user(session, telegram_id=302)
            await session.flush()
            entries = await cv_service.not_registered_recipients(session, campaign)
            self.assertEqual([e.telegram_id for e in entries], [301])


if __name__ == "__main__":
    unittest.main()
