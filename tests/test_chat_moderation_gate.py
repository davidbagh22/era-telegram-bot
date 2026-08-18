from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import User
from app.handlers.chat import general_chat_quick_navigation, moderation_gate
from app.utils.constants import ApplicationStatus, Role


def _settings(**overrides) -> SimpleNamespace:
    defaults = dict(
        general_chat_id=-1001,
        internal_department_chat_id=-1002,
        external_department_chat_id=None,
        leaders_chat_id=None,
        effective_miniapp_url="https://era.example/app/",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class FakeMessage:
    def __init__(self, *, chat_id: int, telegram_id: int | None, text: str = "hello") -> None:
        self.chat = SimpleNamespace(id=chat_id, type="supergroup")
        self.from_user = SimpleNamespace(id=telegram_id) if telegram_id is not None else None
        self.text = text
        self.date = None
        self.deleted = False
        self.replies: list[str] = []

    async def delete(self) -> None:
        self.deleted = True

    async def reply(self, text: str, **kwargs) -> None:
        self.replies.append(text)

    async def answer(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class ChatModerationGateTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_unregistered_general_chat_member_is_never_restricted_or_deleted(self) -> None:
        """ToR §1/§17: the general chat must stay a normal chat for people
        who simply haven't registered yet."""
        async with self.session_factory() as session:
            bot = AsyncMock()
            message = FakeMessage(chat_id=-1001, telegram_id=999)

            await moderation_gate(message, bot, None, _settings(), session)

            self.assertFalse(message.deleted)
            bot.restrict_chat_member.assert_not_called()
            bot.send_message.assert_not_called()

    async def test_pending_general_chat_member_is_never_restricted_or_deleted(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.PENDING)
            bot = AsyncMock()
            message = FakeMessage(chat_id=-1001, telegram_id=user.telegram_id)

            await moderation_gate(message, bot, user, _settings(), session)

            self.assertFalse(message.deleted)
            bot.restrict_chat_member.assert_not_called()

    async def test_rejected_general_chat_member_still_gets_restricted(self) -> None:
        """The grace period is only for not_registered/not_approved --
        REJECTED keeps the existing enforcement (removal itself happens via
        sync_user_chat_access, not here; this handler still restricts as a
        safety net for stray messages)."""
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.REJECTED)
            bot = AsyncMock()
            message = FakeMessage(chat_id=-1001, telegram_id=user.telegram_id)

            await moderation_gate(message, bot, user, _settings(), session)

            self.assertTrue(message.deleted)
            bot.restrict_chat_member.assert_awaited_once()

    async def test_grace_period_does_not_apply_outside_general_chat(self) -> None:
        """An unregistered person posting in the internal-department chat
        (a legitimately narrow, gated chat) is still restricted -- the
        grace period is specific to the general chat this ToR is about."""
        async with self.session_factory() as session:
            bot = AsyncMock()
            message = FakeMessage(chat_id=-1002, telegram_id=999)

            await moderation_gate(message, bot, None, _settings(), session)

            self.assertTrue(message.deleted)
            bot.restrict_chat_member.assert_awaited_once()

    async def test_approved_member_is_unaffected(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.APPROVED)
            bot = AsyncMock()
            message = FakeMessage(chat_id=-1001, telegram_id=user.telegram_id, text="привет всем")

            await moderation_gate(message, bot, user, _settings(), session)

            self.assertFalse(message.deleted)
            bot.restrict_chat_member.assert_not_called()

    async def test_quick_nav_grace_period_deletes_trigger_but_does_not_restrict(self) -> None:
        bot = AsyncMock()
        message = FakeMessage(chat_id=-1001, telegram_id=999, text="📅 События")

        await general_chat_quick_navigation(message, bot, None, _settings())

        self.assertTrue(message.deleted)
        bot.restrict_chat_member.assert_not_called()
        bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
