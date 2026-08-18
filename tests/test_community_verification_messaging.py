from __future__ import annotations

import unittest
from datetime import timedelta
from types import SimpleNamespace

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.chat_moderation import CommunityVerificationDelivery
from app.database.models import AuditLog, User
from app.services import community_verification_service as cv_service
from app.utils.constants import ApplicationStatus, Role


def _method(chat_id: int = 1) -> SendMessage:
    return SendMessage(chat_id=chat_id, text="test")


class FakeMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeBot:
    def __init__(self, failures: dict[int, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.sent: list[int] = []
        self.pinned: list[tuple[int, int]] = []
        self._next_message_id = 1000
        self.pin_should_fail = False

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> FakeMessage:
        self.sent.append(chat_id)
        if chat_id in self.failures:
            raise self.failures[chat_id]
        self._next_message_id += 1
        return FakeMessage(self._next_message_id)

    async def pin_chat_message(self, chat_id: int, message_id: int, disable_notification=None) -> None:
        if self.pin_should_fail:
            raise TelegramAPIError(method=_method(chat_id), message="cannot pin")
        self.pinned.append((chat_id, message_id))


def _settings(**overrides) -> SimpleNamespace:
    defaults = dict(general_chat_id=-1001)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class CommunityVerificationMessagingTests(unittest.IsolatedAsyncioTestCase):
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
            application_status=ApplicationStatus.APPROVED,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_launch_wave_sends_to_every_eligible_user_once(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            await self._make_user(session, telegram_id=1)
            await self._make_user(session, telegram_id=2)
            bot = FakeBot()

            result = await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)

            self.assertEqual(result.sent, 2)
            self.assertEqual(sorted(bot.sent), [1, 2])
            rows = (await session.scalars(select(CommunityVerificationDelivery))).all()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row.status == "sent" for row in rows))

    async def test_launch_wave_is_idempotent_on_second_call(self) -> None:
        """ToR §56: never send the launch message twice to the same person."""
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            await self._make_user(session, telegram_id=1)
            bot = FakeBot()

            first = await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)
            second = await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)

            self.assertEqual(first.sent, 1)
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.already_attempted, 1)
            self.assertEqual(bot.sent, [1])  # never called a second time

    async def test_launch_wave_classifies_blocked_and_unreachable(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            await self._make_user(session, telegram_id=1)
            await self._make_user(session, telegram_id=2)
            bot = FakeBot(
                failures={
                    1: TelegramForbiddenError(method=_method(1), message="bot was blocked by the user"),
                }
            )

            result = await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)

            self.assertEqual(result.sent, 1)
            self.assertEqual(result.blocked, 1)
            rows = {
                row.telegram_id: row.status
                for row in (await session.scalars(select(CommunityVerificationDelivery))).all()
            }
            self.assertEqual(rows[1], "blocked")
            self.assertEqual(rows[2], "sent")

    async def test_launch_wave_never_fails_campaign_on_unreachable_user(self) -> None:
        """ToR §13: an unreachable recipient is not a fatal error."""
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            await self._make_user(session, telegram_id=1)
            bot = FakeBot(failures={1: TelegramForbiddenError(method=_method(1), message="blocked")})

            result = await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)
            self.assertEqual(result.blocked, 1)
            refreshed = await cv_service.latest_campaign(session)
            self.assertEqual(refreshed.status, "active")

    async def test_reminder_wave_only_targets_unregistered_notified_people(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            await self._make_user(session, telegram_id=1)  # already registered
            bot = FakeBot()
            await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=999, kind="initial", status="sent"
                )
            )
            await session.flush()

            result = await cv_service.send_reminder_wave(session, bot, campaign, actor_id=1)

            self.assertEqual(result.sent, 1)
            self.assertEqual(bot.sent, [1, 999])  # 1 from launch wave, 999 from reminder

    async def test_reminder_wave_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=campaign.id, telegram_id=999, kind="initial", status="sent"
                )
            )
            await session.flush()
            bot = FakeBot()

            first = await cv_service.send_reminder_wave(session, bot, campaign)
            second = await cv_service.send_reminder_wave(session, bot, campaign)

            self.assertEqual(first.sent, 1)
            self.assertEqual(second.sent, 0)
            self.assertEqual(bot.sent, [999])

    async def test_post_launch_pin_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            bot = FakeBot()

            first = await cv_service.post_launch_pin(session, bot, _settings(), campaign, actor_id=1)
            second = await cv_service.post_launch_pin(session, bot, _settings(), campaign, actor_id=1)

            self.assertEqual(first, "posted")
            self.assertEqual(second, "already_posted")
            self.assertEqual(len(bot.pinned), 1)

    async def test_post_launch_pin_noop_without_bound_general_chat(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            bot = FakeBot()
            posted = await cv_service.post_launch_pin(
                session, bot, _settings(general_chat_id=None), campaign, actor_id=1
            )
            self.assertEqual(posted, "no_chat_bound")
            self.assertEqual(bot.sent, [])

    async def test_post_launch_pin_failure_stays_retryable(self) -> None:
        """Unlike personal DMs, a failed pin attempt must not be
        permanently recorded -- ToR §8 wants exactly one pin, but a bot
        temporarily lacking pin rights shouldn't burn the only attempt. Also
        confirms "failed" and "already_posted" are distinguishable outcomes
        (a plain bool previously conflated them -- caught via live browser
        verification against a bot with an invalid token)."""
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            bot = FakeBot()
            bot.pin_should_fail = True

            first = await cv_service.post_launch_pin(session, bot, _settings(), campaign, actor_id=1)
            self.assertEqual(first, "failed")

            bot.pin_should_fail = False
            second = await cv_service.post_launch_pin(session, bot, _settings(), campaign, actor_id=1)
            self.assertEqual(second, "posted")

    async def test_run_verification_reminders_only_fires_within_last_24h(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            campaign.ends_at = campaign.ends_at.__class__.now(campaign.ends_at.tzinfo) + timedelta(hours=48)
            await session.flush()
            await session.commit()

        class FactoryWrapper:
            def __init__(self, factory):
                self.factory = factory

            def __call__(self):
                return self.factory()

        bot = FakeBot()
        await cv_service.run_verification_reminders(bot, _settings(), FactoryWrapper(self.session_factory))
        self.assertEqual(bot.sent, [])  # more than 24h left -- no reminder yet

        async with self.session_factory() as session:
            fresh = await cv_service.latest_campaign(session)
            fresh.ends_at = fresh.ends_at.__class__.now(fresh.ends_at.tzinfo) + timedelta(hours=10)
            session.add(
                CommunityVerificationDelivery(
                    campaign_id=fresh.id, telegram_id=555, kind="initial", status="sent"
                )
            )
            await session.flush()
            await session.commit()

        await cv_service.run_verification_reminders(bot, _settings(), FactoryWrapper(self.session_factory))
        self.assertEqual(bot.sent, [555])

    async def test_launch_wave_audit_logged(self) -> None:
        async with self.session_factory() as session:
            campaign = await cv_service.start_campaign(session, window_hours=72, started_by=1)
            await self._make_user(session, telegram_id=1)
            bot = FakeBot()
            await cv_service.send_launch_wave(session, bot, campaign, actor_id=1)
            actions = (await session.scalars(select(AuditLog.action))).all()
            self.assertIn("community_verification.launch_sent", actions)


if __name__ == "__main__":
    unittest.main()
