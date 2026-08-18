from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.content.era_public_pack import load_era_public_pack
from app.database import Base
from app.database.media_models import (
    MediaChannelDelivery,
    MediaContentItem,
    MediaContentTask,
    MediaLibraryItem,
    MediaRequest,
)
from app.database.models import Department, Direction, Event, Task, TaskParticipant, User, UserDirection
from app.services import media_service, task_service
from app.services.chat_registry_service import ChatHealthResult
from app.services.media_dashboard_service import seed_media_guide
from app.utils.constants import ApplicationStatus, Role


class MediaOsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            bot_token="1234567890:test-token",
            era_channel_id=-100123456789,
            media_chat_id=-100987654321,
        )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def test_authored_pack_is_exactly_26_weeks_104_items_and_26_polls(self) -> None:
        pack = load_era_public_pack()
        items = pack["items"]
        self.assertEqual(pack["timezone"], "Asia/Yerevan")
        self.assertEqual(pack["start_date"], "2026-08-17")
        self.assertEqual(len(items), 104)
        self.assertEqual({item["week"] for item in items}, set(range(1, 27)))
        self.assertEqual(sum(item["kind"] == "poll" for item in items), 26)

    async def test_seed_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            await media_service.seed_media_os(session, self.settings)
            await media_service.seed_media_os(session, self.settings)
            content_count = int(
                await session.scalar(select(func.count(MediaContentItem.id))) or 0
            )
            poll_count = int(
                await session.scalar(
                    select(func.count(MediaContentItem.id)).where(
                        MediaContentItem.kind == "poll"
                    )
                )
                or 0
            )
            self.assertEqual(content_count, 104)
            self.assertEqual(poll_count, 26)

    async def test_seed_media_guide_is_internal_route_and_idempotent(self) -> None:
        # DELTA ToR §32-34: the Guide item must be an in-app hash route, not
        # a full external URL -- opening it externally drops Telegram
        # initData (the reported "empty_init_data" bug).
        async with self.session_factory() as session:
            await seed_media_guide(session, self.settings)
            await seed_media_guide(session, self.settings)
            rows = (
                await session.scalars(
                    select(MediaLibraryItem).where(MediaLibraryItem.title == "Гайд Media ЭРА")
                )
            ).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].destination_type, "internal_route")
            self.assertEqual(rows[0].url, "media/guide")

    async def test_seed_media_guide_heals_a_stale_external_url_row(self) -> None:
        # Simulates an environment seeded before this fix, where the row was
        # created with a full external URL -- re-seeding must correct it in
        # place rather than leaving the old bug permanently deployed.
        async with self.session_factory() as session:
            session.add(
                MediaLibraryItem(
                    kind="guide",
                    category="guides",
                    title="Гайд Media ЭРА",
                    description="stale",
                    url="https://app.example.com/#/media/guide",
                    destination_type="external_url",
                    sort_order=25,
                    is_active=True,
                )
            )
            await session.flush()

            await seed_media_guide(session, self.settings)

            row = await session.scalar(
                select(MediaLibraryItem).where(MediaLibraryItem.title == "Гайд Media ЭРА")
            )
            self.assertEqual(row.destination_type, "internal_route")
            self.assertEqual(row.url, "media/guide")

    async def test_approved_participant_gets_hub_but_not_desk(self) -> None:
        async with self.session_factory() as session:
            user = User(
                telegram_id=1,
                first_name="Member",
                application_status=ApplicationStatus.APPROVED,
                role=Role.PARTICIPANT,
            )
            session.add(user)
            await session.flush()
            self.assertFalse(await media_service.can_manage_media(session, user, self.settings))

            admin = User(
                telegram_id=2,
                first_name="Admin",
                application_status=ApplicationStatus.APPROVED,
                role=Role.ADMIN,
            )
            session.add(admin)
            await session.flush()
            self.assertTrue(await media_service.can_manage_media(session, admin, self.settings))

    async def test_media_access_level_tiers(self) -> None:
        # DELTA ToR §27-31: hub access is no longer "any approved
        # participant" -- it's a real NO_ACCESS -> PENDING -> MEDIA_MEMBER
        # tier, built on the existing Direction/UserDirection model, plus
        # MEDIA_LEADER (direction leader / configured manager) and ADMIN.
        async with self.session_factory() as session:
            department = Department(name="Внешние связи")
            session.add(department)
            await session.flush()
            direction = Direction(department_id=department.id, name="Медиа")
            session.add(direction)
            await session.flush()

            plain = User(telegram_id=1, first_name="Plain", application_status=ApplicationStatus.APPROVED)
            pending = User(telegram_id=2, first_name="Pending", application_status=ApplicationStatus.APPROVED)
            member = User(telegram_id=3, first_name="Member", application_status=ApplicationStatus.APPROVED)
            leader = User(telegram_id=4, first_name="Leader", application_status=ApplicationStatus.APPROVED)
            admin = User(telegram_id=5, first_name="Admin", application_status=ApplicationStatus.APPROVED, role=Role.ADMIN)
            not_approved = User(telegram_id=6, first_name="Rejected", application_status=ApplicationStatus.PENDING)
            session.add_all([plain, pending, member, leader, admin, not_approved])
            await session.flush()

            direction.leader_id = leader.id
            session.add(UserDirection(user_id=pending.id, direction_id=direction.id, status="pending"))
            session.add(UserDirection(user_id=member.id, direction_id=direction.id, status="approved"))
            await session.flush()

            self.assertEqual(await media_service.media_access_level(session, plain, self.settings), "no_access")
            self.assertEqual(await media_service.media_access_level(session, pending, self.settings), "pending")
            self.assertEqual(await media_service.media_access_level(session, member, self.settings), "member")
            self.assertEqual(await media_service.media_access_level(session, leader, self.settings), "leader")
            self.assertEqual(await media_service.media_access_level(session, admin, self.settings), "admin")
            self.assertEqual(await media_service.media_access_level(session, not_approved, self.settings), "no_access")
            self.assertEqual(await media_service.media_access_level(session, None, self.settings), "no_access")

            self.assertFalse(media_service.can_use_media_hub("no_access"))
            self.assertFalse(media_service.can_use_media_hub("pending"))
            self.assertTrue(media_service.can_use_media_hub("member"))
            self.assertTrue(media_service.can_use_media_hub("leader"))
            self.assertTrue(media_service.can_use_media_hub("admin"))

    async def test_apply_for_media_is_idempotent_and_decide_flow_round_trips(self) -> None:
        async with self.session_factory() as session:
            department = Department(name="Внешние связи")
            session.add(department)
            await session.flush()
            direction = Direction(department_id=department.id, name="Медиа")
            session.add(direction)
            await session.flush()

            user = User(telegram_id=1, first_name="Applicant", application_status=ApplicationStatus.APPROVED)
            session.add(user)
            await session.flush()

            level = await media_service.apply_for_media(session, user)
            self.assertEqual(level, "pending")
            # Re-applying while pending must not create a second row.
            level_again = await media_service.apply_for_media(session, user)
            self.assertEqual(level_again, "pending")
            applications = await media_service.list_media_applications(session)
            self.assertEqual([applicant.id for applicant, _ in applications], [user.id])

            await media_service.decide_media_application(session, user.id, "approve")
            self.assertEqual(
                await media_service.media_access_level(session, user, self.settings), "member"
            )
            members = await media_service.list_media_members(session)
            self.assertEqual([member.id for member in members], [user.id])

            # Applying again once already a member is a no-op, not a demotion.
            level_after_membership = await media_service.apply_for_media(session, user)
            self.assertEqual(level_after_membership, "member")

            await media_service.decide_media_application(session, user.id, "revoke")
            self.assertEqual(
                await media_service.media_access_level(session, user, self.settings), "no_access"
            )

            with self.assertRaises(ValueError):
                await media_service.decide_media_application(session, 999999, "reject")

    async def test_media_task_reuses_task_engine_and_claim_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            manager = User(telegram_id=10, first_name="Manager", role=Role.ADMIN)
            member = User(
                telegram_id=11,
                first_name="Member",
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([manager, member])
            await session.flush()
            item = await media_service.create_content(
                session,
                creator_id=manager.id,
                body="Публикация",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=3),
            )
            links = await media_service.create_content_tasks(
                session, item, creator_id=manager.id, task_kinds=["text"]
            )
            self.assertEqual(len(links), 1)
            task = await session.get(Task, links[0].task_id)
            self.assertIsNotNone(task)
            self.assertTrue(task.reward_json["media_task"])

            membership, error = await task_service.claim(session, task, member)
            self.assertIsNone(error)
            self.assertEqual(membership.status, "joined")
            _, repeat_error = await task_service.claim(session, task, member)
            self.assertEqual(repeat_error, "already_joined")
            participant_count = int(
                await session.scalar(
                    select(func.count(TaskParticipant.id)).where(
                        TaskParticipant.task_id == task.id,
                        TaskParticipant.user_id == member.id,
                    )
                )
                or 0
            )
            self.assertEqual(participant_count, 1)

    async def test_event_media_request_is_idempotent_and_full_package_creates_six_tasks(self) -> None:
        async with self.session_factory() as session:
            owner = User(
                telegram_id=20,
                first_name="Owner",
                application_status=ApplicationStatus.APPROVED,
            )
            session.add(owner)
            await session.flush()
            event = Event(
                title="ERA Event",
                description="Description",
                event_date=date.today() + timedelta(days=14),
                event_time=time(18, 0),
                location="Дом Москвы",
                format="offline",
                created_by=owner.id,
            )
            session.add(event)
            await session.flush()

            first = await media_service.request_media_package(
                session,
                source_type="event",
                source_id=event.id,
                package_type="full",
                requester=owner,
                settings=self.settings,
            )
            second = await media_service.request_media_package(
                session,
                source_type="event",
                source_id=event.id,
                package_type="full",
                requester=owner,
                settings=self.settings,
            )
            self.assertEqual(first.id, second.id)
            request_count = int(
                await session.scalar(select(func.count(MediaRequest.id))) or 0
            )
            task_count = int(
                await session.scalar(
                    select(func.count(MediaContentTask.id)).where(
                        MediaContentTask.content_id == first.content_id
                    )
                )
                or 0
            )
            self.assertEqual(request_count, 1)
            self.assertEqual(task_count, 6)

    async def test_authored_text_is_published_once(self) -> None:
        async with self.session_factory() as session:
            item = MediaContentItem(
                source_kind="authored_pack",
                source_key="test:text",
                kind="text",
                body="Тест публикации",
                scheduled_at=datetime.now(timezone.utc),
                status="scheduled",
                poll_options=[],
                metadata_json={"approved": True},
            )
            session.add(item)
            await session.commit()
            bot = SimpleNamespace(
                send_message=AsyncMock(return_value=SimpleNamespace(message_id=777)),
                send_poll=AsyncMock(),
            )
            first = await media_service.publish_content(
                session, bot, self.settings, item, manual=False
            )
            second = await media_service.publish_content(
                session, bot, self.settings, item, manual=False
            )
            self.assertTrue(first.ok)
            self.assertFalse(second.ok)
            self.assertEqual(second.code, "already_published")
            self.assertEqual(bot.send_message.await_count, 1)
            delivery_count = int(
                await session.scalar(select(func.count(MediaChannelDelivery.id))) or 0
            )
            self.assertEqual(delivery_count, 1)

    async def test_sunday_content_uses_native_poll(self) -> None:
        async with self.session_factory() as session:
            item = MediaContentItem(
                source_kind="authored_pack",
                source_key="test:poll",
                kind="poll",
                poll_question="Что выберешь?",
                poll_options=["Первое", "Второе"],
                scheduled_at=datetime.now(timezone.utc),
                status="scheduled",
                metadata_json={"approved": True},
            )
            session.add(item)
            await session.commit()
            bot = SimpleNamespace(
                send_message=AsyncMock(),
                send_poll=AsyncMock(return_value=SimpleNamespace(message_id=778)),
            )
            result = await media_service.publish_content(
                session, bot, self.settings, item, manual=False
            )
            self.assertTrue(result.ok)
            bot.send_poll.assert_awaited_once()
            bot.send_message.assert_not_awaited()

    async def test_manual_content_is_never_auto_published(self) -> None:
        async with self.session_factory() as session:
            item = MediaContentItem(
                source_kind="manual",
                source_key="test:manual",
                kind="text",
                body="Ручной материал",
                scheduled_at=datetime.now(timezone.utc),
                status="scheduled",
                poll_options=[],
                metadata_json={},
            )
            session.add(item)
            await session.flush()
            bot = SimpleNamespace(send_message=AsyncMock(), send_poll=AsyncMock())
            result = await media_service.publish_content(
                session, bot, self.settings, item, manual=False
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.code, "auto_authored_only")
            bot.send_message.assert_not_awaited()

    async def test_auto_cannot_enable_without_channel_post_rights(self) -> None:
        async with self.session_factory() as session:
            bot = SimpleNamespace()
            with patch(
                "app.services.media_service.check_chats_health",
                new=AsyncMock(
                    return_value=[
                        ChatHealthResult(
                            chat_key="era_channel",
                            ok=False,
                            detail="cannot_post_messages",
                        )
                    ]
                ),
            ):
                with self.assertRaisesRegex(ValueError, "channel_not_ready"):
                    await media_service.set_auto_enabled(
                        session, bot, self.settings, enabled=True
                    )

    async def test_auto_can_enable_when_channel_is_ready(self) -> None:
        async with self.session_factory() as session:
            bot = SimpleNamespace()
            with patch(
                "app.services.media_service.check_chats_health",
                new=AsyncMock(
                    return_value=[
                        ChatHealthResult(
                            chat_key="era_channel", ok=True, detail="ok:post+edit"
                        )
                    ]
                ),
            ):
                config = await media_service.set_auto_enabled(
                    session, bot, self.settings, enabled=True
                )
            self.assertTrue(config["auto_enabled"])


if __name__ == "__main__":
    unittest.main()
