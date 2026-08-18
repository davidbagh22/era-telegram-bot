from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AuditLog, User
from app.handlers.chat import handle_chat_join_request
from app.services.chat_access_service import sync_user_chat_access
from app.utils.constants import ApplicationStatus, Role


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        general_chat_id=-1001,
        internal_department_chat_id=None,
        external_department_chat_id=None,
        leaders_chat_id=None,
        chat_ids={-1001},
        era_channel_url="https://t.me/era_channel",
    )


class ChatAccessAuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, **overrides) -> User:
        defaults = dict(
            telegram_id=10,
            first_name="Dev",
            last_name=None,
            phone="+10000000000",
            city="City",
            education_work="Work",
            occupation="Occupation",
            motivation="Motivation",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_sync_writes_audit_summary_row(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            bot = AsyncMock()

            fixed, failed = await sync_user_chat_access(bot, _settings(), session, user)

            self.assertEqual(fixed, 1)
            self.assertEqual(failed, 0)
            rows = (
                await session.scalars(
                    select(AuditLog).where(AuditLog.action == "chat_access.synced")
                )
            ).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].actor_id, user.id)
            self.assertEqual(rows[0].new_value["fixed"], 1)
            self.assertEqual(rows[0].new_value["failed"], 0)

    async def test_sync_records_failures_for_visibility(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            bot = AsyncMock()
            bot.restrict_chat_member = AsyncMock(
                side_effect=TelegramAPIError(method=object(), message="telegram down")
            )
            # An unapproved user forces a restrict_member call, which will
            # fail via the mocked exception above.
            user.application_status = ApplicationStatus.PENDING

            fixed, failed = await sync_user_chat_access(bot, _settings(), session, user)

            self.assertEqual(failed, 1)
            rows = (
                await session.scalars(
                    select(AuditLog).where(AuditLog.action == "chat_access.synced")
                )
            ).all()
            self.assertEqual(rows[0].new_value["failed"], 1)

    async def test_sync_removes_rejected_user_from_general_chat(self) -> None:
        """ToR §3/§62: a rejected applicant already in the general chat gets
        actually removed (ban+immediately-unban), not just muted."""
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.REJECTED)
            bot = AsyncMock()

            fixed, failed = await sync_user_chat_access(bot, _settings(), session, user)

            self.assertEqual(fixed, 1)
            self.assertEqual(failed, 0)
            bot.ban_chat_member.assert_awaited_once_with(chat_id=-1001, user_id=user.telegram_id)
            bot.unban_chat_member.assert_awaited_once_with(
                chat_id=-1001, user_id=user.telegram_id, only_if_banned=True
            )
            bot.restrict_chat_member.assert_not_called()

    async def test_sync_still_restricts_pending_user_not_removes(self) -> None:
        """Only REJECTED triggers removal -- not_approved (still PENDING)
        keeps the existing mute-only behavior."""
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.PENDING)
            bot = AsyncMock()

            await sync_user_chat_access(bot, _settings(), session, user)

            bot.restrict_chat_member.assert_awaited_once()
            bot.ban_chat_member.assert_not_called()


class ChatJoinRequestAuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, **overrides) -> User:
        defaults = dict(
            telegram_id=10,
            first_name="Dev",
            last_name=None,
            phone="+10000000000",
            city="City",
            education_work="Work",
            occupation="Occupation",
            motivation="Motivation",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    def _request(self, *, chat_id: int, telegram_id: int) -> SimpleNamespace:
        return SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            from_user=SimpleNamespace(id=telegram_id),
        )

    async def test_approved_join_request_is_audited(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            bot = AsyncMock()
            request = self._request(chat_id=-1001, telegram_id=user.telegram_id)

            await handle_chat_join_request(request, bot, _settings(), session)

            rows = (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "chat_access.join_request_approved"
                    )
                )
            ).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].new_value["telegram_id"], user.telegram_id)
            bot.approve_chat_join_request.assert_awaited_once()

    async def test_declined_join_request_is_audited(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.REJECTED)
            bot = AsyncMock()
            request = self._request(chat_id=-1001, telegram_id=user.telegram_id)

            await handle_chat_join_request(request, bot, _settings(), session)

            rows = (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "chat_access.join_request_declined"
                    )
                )
            ).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].new_value["reason"], "rejected")
            bot.decline_chat_join_request.assert_awaited_once()

    async def test_unregistered_join_request_gets_rich_onboarding_dm(self) -> None:
        """ToR §22-24: a brand-new person (no User row at all) gets the full
        "what is ЭРА" pitch with a real "Начать регистрацию" button, not the
        generic one-line access_message()."""
        async with self.session_factory() as session:
            bot = AsyncMock()
            request = self._request(chat_id=-1001, telegram_id=999)

            await handle_chat_join_request(request, bot, _settings(), session)

            bot.send_message.assert_awaited_once()
            call = bot.send_message.await_args
            self.assertEqual(call.args[0], 999)
            self.assertIn("Хотите в ЭРА", call.args[1])
            markup = call.kwargs["reply_markup"]
            self.assertEqual(markup.inline_keyboard[0][0].callback_data, "registration:start")

    async def test_pending_applicant_join_request_gets_status_dm(self) -> None:
        """ToR §26: someone who already registered and is on
        PENDING/NEEDS_INFO must never be told to register again."""
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.PENDING)
            bot = AsyncMock()
            request = self._request(chat_id=-1001, telegram_id=user.telegram_id)

            await handle_chat_join_request(request, bot, _settings(), session)

            bot.send_message.assert_awaited_once()
            call = bot.send_message.await_args
            self.assertIn("Заявка уже у команды ЭРА", call.args[1])
            markup = call.kwargs["reply_markup"]
            self.assertEqual(markup.inline_keyboard[0][0].callback_data, "registration:status")

    async def test_rejected_join_request_keeps_generic_short_message(self) -> None:
        """ToR §27: decline stays on the existing generic access_message()
        -- no new registration prompt for a rejected applicant."""
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.REJECTED)
            bot = AsyncMock()
            request = self._request(chat_id=-1001, telegram_id=user.telegram_id)

            await handle_chat_join_request(request, bot, _settings(), session)

            bot.send_message.assert_awaited_once()
            call = bot.send_message.await_args
            self.assertNotIn("Хотите в ЭРА", call.args[1])
            self.assertNotIn("reply_markup", call.kwargs)


if __name__ == "__main__":
    unittest.main()
