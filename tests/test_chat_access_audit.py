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

    async def test_sync_preserves_moderator_restrictions(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            bot = AsyncMock()
            bot.get_chat_member.return_value = SimpleNamespace(
                status="restricted", is_member=True
            )

            fixed, failed = await sync_user_chat_access(
                bot, _settings(), session, user
            )

            self.assertEqual((fixed, failed), (0, 1))
            bot.restrict_chat_member.assert_not_awaited()
            rows = (
                await session.scalars(
                    select(AuditLog).where(AuditLog.action == "chat_access.synced")
                )
            ).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].new_value["failed"], 1)

    async def test_restricted_pending_user_is_not_unmuted(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, application_status=ApplicationStatus.PENDING
            )
            bot = AsyncMock()
            bot.get_chat_member.return_value = SimpleNamespace(
                status="restricted", is_member=True
            )
            fixed, failed = await sync_user_chat_access(
                bot, _settings(), session, user
            )
            self.assertEqual((fixed, failed), (0, 1))
            bot.restrict_chat_member.assert_not_awaited()


    async def test_regular_member_is_not_modified(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            bot = AsyncMock()
            bot.get_chat_member.return_value = SimpleNamespace(status="member")
            fixed, failed = await sync_user_chat_access(bot, _settings(), session, user)
            self.assertEqual((fixed, failed), (1, 0))
            bot.restrict_chat_member.assert_not_awaited()

    async def test_absent_member_is_not_modified(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            bot = AsyncMock()
            bot.get_chat_member.return_value = SimpleNamespace(status="left")
            fixed, failed = await sync_user_chat_access(bot, _settings(), session, user)
            self.assertEqual((fixed, failed), (0, 1))
            bot.restrict_chat_member.assert_not_awaited()

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


if __name__ == "__main__":
    unittest.main()
