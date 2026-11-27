"""#321 prep: content store, publish flag OFF, admin preview, opt-out safety."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, User
from app.database.system_models import NotificationDelivery
from app.handlers.book_club import change_subscription
from app.services import book_club_service as club
from app.services.book_club_service import daily_job
from app.services.literature_48_laws_service import (
    TARGET_COUNT,
    admin_preview_payload,
    content_progress,
    get_analysis,
    list_analyses,
    next_unpublished_analysis,
    publish_enabled,
    render_analysis,
    subscriber_delivery_key,
    task_points_idempotency_key,
    topic_delivery_key,
    validate_store,
)
from app.utils.constants import ApplicationStatus


def test_content_store_has_48_complete_analyses_with_null_audio():
    validate_store()
    progress = content_progress()
    assert progress["target_count"] == TARGET_COUNT
    assert progress["complete_count"] == TARGET_COUNT
    assert progress["is_complete"] is True
    assert progress["missing_law_numbers"] == []
    assert progress["audio_url_null_count"] == TARGET_COUNT
    assert progress["audio_url_set_count"] == 0
    assert progress["publish_seed_enabled"] is False

    analyses = list_analyses(complete_only=True)
    assert len(analyses) == 48
    titles = {item.title for item in analyses}
    assert len(titles) == 48
    for item in analyses:
        assert item.audio_url is None
        assert item.case_study.strip()
        assert item.critical_view.strip()
        assert item.discussion_question.strip()
        html = render_analysis(item.law_number)
        assert f"Закон {item.law_number}/48" in html
        assert "не приложено" in html
        assert len(html) < 4096


def test_idempotency_keys_are_stable_and_distinct():
    start = date(2026, 10, 10)
    topic_1 = topic_delivery_key(start, 1)
    topic_2 = topic_delivery_key(start, 2)
    assert topic_1 == "issue:2026-10-10:1"
    assert topic_1 != topic_2
    assert subscriber_delivery_key(start, 1, 7) == "book-club:2026-10-10:1:7"
    assert subscriber_delivery_key(start, 1, 7) != subscriber_delivery_key(start, 1, 8)
    assert task_points_idempotency_key(3, 5) == task_points_idempotency_key(3, 5)
    assert task_points_idempotency_key(3, 5) != task_points_idempotency_key(3, 6)


def test_publish_flag_defaults_off():
    settings = Settings(bot_token="1234567890:test-token")
    assert settings.literature_48_laws_publish_enabled is False
    assert publish_enabled(settings) is False
    settings_on = Settings(
        bot_token="1234567890:test-token",
        literature_48_laws_publish_enabled=True,
    )
    assert publish_enabled(settings_on) is True


class Literature48PrepTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            bot_token="1234567890:test-token",
            general_chat_id=-100123,
            literature_48_laws_publish_enabled=False,
        )
        self.bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as session:
            session.add_all([
                User(
                    id=i,
                    telegram_id=100 + i,
                    first_name="Test",
                    book_club_subscribed=i != 4,
                    application_status=(
                        ApplicationStatus.PENDING if i == 5 else ApplicationStatus.APPROVED
                    ),
                    is_archived=i == 2,
                    is_blocked=i == 3,
                )
                for i in range(1, 6)
            ])
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def callback(self, data):
        return SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )

    async def approve_today(self):
        async with self.sessions() as session:
            await club.approve_series_issue(
                session,
                on_date=date(2026, 10, 10),
                chat_id=self.settings.general_chat_id,
                number=1,
                actor_id=1,
            )
            await session.commit()

    async def test_flag_off_blocks_send_even_when_approved(self):
        await self.approve_today()
        with patch("app.services.book_club_service.datetime") as clock, patch(
            "app.services.book_club_service.send_general_topic", new=AsyncMock()
        ) as topic:
            clock.now.return_value = datetime(2026, 10, 10, 19, tzinfo=ZoneInfo("Asia/Yerevan"))
            await daily_job(self.bot, self.settings, self.sessions)
        topic.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()
        async with self.sessions() as session:
            # Program start must not be initialized by a gated no-op run.
            assert await session.scalar(
                select(AppSetting).where(AppSetting.key == "book_club_start_date")
            ) is None

    async def test_flag_on_with_approval_sends_once_and_respects_opt_out(self):
        self.settings = Settings(
            bot_token="1234567890:test-token",
            general_chat_id=-100123,
            literature_48_laws_publish_enabled=True,
        )
        await self.approve_today()
        with patch("app.services.book_club_service.datetime") as clock, patch(
            "app.services.notification_service._session_factory", return_value=self.sessions
        ), patch(
            "app.services.book_club_service.send_general_topic",
            new=AsyncMock(return_value=True),
        ):
            clock.now.return_value = datetime(2026, 10, 10, 19, tzinfo=ZoneInfo("Asia/Yerevan"))
            await daily_job(self.bot, self.settings, self.sessions)
            await daily_job(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.call_args
        assert args[0] == 101
        assert "Выпуск 1/48" in args[1]
        assert kwargs["parse_mode"] == "HTML"

        async with self.sessions() as session:
            user = await session.get(User, 1)
            await change_subscription(self.callback("bookclub:unsubscribe"), user, session)
            await change_subscription(self.callback("bookclub:unsubscribe"), user, session)
            assert not user.book_club_subscribed

        self.bot.send_message.reset_mock()
        # Re-run after opt-out: topic may already_sent; subscriber must not get DM.
        with patch("app.services.book_club_service.datetime") as clock, patch(
            "app.services.notification_service._session_factory", return_value=self.sessions
        ), patch(
            "app.services.book_club_service.send_general_topic",
            new=AsyncMock(return_value=True),
        ):
            clock.now.return_value = datetime(2026, 10, 10, 19, tzinfo=ZoneInfo("Asia/Yerevan"))
            await daily_job(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_not_awaited()

    async def test_admin_preview_shows_next_unpublished_without_send(self):
        async with self.sessions() as session:
            session.add(
                NotificationDelivery(
                    delivery_key="general-topic:literature:issue:2026-10-10:1",
                    chat_id=-100123,
                    notification_type="general_topic",
                    status="sent",
                    message_id=99,
                    payload_hash="fixture",
                    attempt_count=1,
                )
            )
            await session.commit()
            nxt = await next_unpublished_analysis(session)
            assert nxt is not None
            assert nxt.law_number == 2
            payload = await admin_preview_payload(session, self.settings)
        assert payload["publish_flag_enabled"] is False
        assert payload["would_public_send"] is False
        assert payload["next_unpublished"]["law_number"] == 2
        assert payload["next_unpublished"]["audio_url"] is None
        assert "Закон 2/48" in payload["preview_html"]
        assert get_analysis(2).title == payload["next_unpublished"]["title"]
        self.bot.send_message.assert_not_awaited()

    async def test_series_status_reports_flag_off_prep_state(self):
        await self.approve_today()
        async with self.sessions() as session:
            status = await club.series_status(
                session, self.settings, on_date=date(2026, 10, 10),
            )
        assert status["publish_flag_enabled"] is False
        assert status["label"] == "Подготовка (флаг OFF)"
        assert status["approved"] is True
        assert "literature_48_laws_publish_enabled=false" in status["reason"]


class Laws48PreviewSendStatusTests(Literature48PrepTests):
    """would_public_send mirrors daily_job blockers; preview stays read-only."""

    DAY = date(2026, 10, 10)

    def flag_on(self):
        self.settings = Settings(
            bot_token="1234567890:test-token",
            general_chat_id=-100123,
            literature_48_laws_publish_enabled=True,
        )

    async def preview(self):
        async with self.sessions() as session:
            return await admin_preview_payload(session, self.settings, on_date=self.DAY)

    async def counts(self):
        async with self.sessions() as session:
            deliveries = len((await session.scalars(select(NotificationDelivery))).all())
            settings_rows = len((await session.scalars(select(AppSetting))).all())
        return deliveries, settings_rows

    async def add_receipt(self, status):
        async with self.sessions() as session:
            session.add(NotificationDelivery(
                delivery_key="general-topic:literature:issue:2026-10-10:1",
                chat_id=-100123, notification_type="general_topic", status=status,
                payload_hash="fixture", attempt_count=1,
            ))
            await session.commit()

    async def test_flag_on_approved_without_blocker_would_send(self):
        self.flag_on()
        await self.approve_today()
        payload = await self.preview()
        assert payload["would_public_send"] is True
        assert payload["editorial_blocks_series"] is False

    async def test_flag_on_unapproved_would_not_send(self):
        self.flag_on()
        assert (await self.preview())["would_public_send"] is False

    async def test_editorial_queue_enabled_or_paused_blocks_send(self):
        self.flag_on()
        await self.approve_today()
        for paused in (False, True):
            async with self.sessions() as session:
                await club.save_editorial_settings(
                    session, actor_id=1, enabled=True, paused=paused,
                )
                await session.commit()
            payload = await self.preview()
            assert payload["calendar_approved"] is True
            assert payload["editorial_blocks_series"] is True
            assert payload["would_public_send"] is False
            assert "редакцион" in payload["series_reason"].lower()
        async with self.sessions() as session:
            await club.save_editorial_settings(session, actor_id=1, enabled=False)
            await session.commit()
        assert (await self.preview())["would_public_send"] is True

    async def test_uncertain_or_conflict_receipt_blocks_send(self):
        self.flag_on()
        await self.approve_today()
        for status in ("uncertain", "conflict"):
            async with self.sessions() as session:
                for row in (await session.scalars(select(NotificationDelivery))).all():
                    await session.delete(row)
                await session.commit()
            await self.add_receipt(status)
            payload = await self.preview()
            assert payload["would_public_send"] is False
            assert payload["receipt_status"] == status

    async def test_already_sent_receipt_does_not_resend(self):
        self.flag_on()
        await self.approve_today()
        await self.add_receipt("sent")
        assert (await self.preview())["would_public_send"] is False

    async def test_preview_is_read_only(self):
        self.flag_on()
        await self.approve_today()
        before = await self.counts()
        await self.preview()
        assert await self.counts() == before
        self.bot.send_message.assert_not_awaited()
