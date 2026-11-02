from app.services.daily_public_content_service import (
    CHANNEL_POSTS,
    CHAT_QUOTES,
    WINDOW_END,
    WINDOW_START,
    scheduled_minute,
    text_for_day,
)


def test_daily_schedule_always_stays_in_moscow_window():
    for day in ("2026-08-29", "2026-08-30", "2027-01-01", "2027-12-31"):
        for kind in ("chat_quote", "channel_post"):
            minute = scheduled_minute(day, kind)
            assert WINDOW_START <= minute < WINDOW_END
            assert minute % 5 == 0


def test_daily_text_is_stable_for_one_calendar_day():
    day = "2026-08-29"
    assert text_for_day(day, "chat_quote") == text_for_day(day, "chat_quote")
    assert text_for_day(day, "channel_post") == text_for_day(day, "channel_post")


def test_content_banks_are_human_and_varied():
    assert len(CHAT_QUOTES) >= 30
    assert len(CHANNEL_POSTS) >= 30
    assert len(set(CHAT_QUOTES)) == len(CHAT_QUOTES)
    assert len(set(CHANNEL_POSTS)) == len(CHANNEL_POSTS)
    assert all("@ERA_1bot" not in item for item in CHAT_QUOTES)
    assert all("@ERA_1bot" not in item for item in CHANNEL_POSTS)


def test_daily_public_content_targets_channel_only():
    source = open("app/services/daily_public_content_service.py", encoding="utf-8").read()
    run_block = source.split("async def run_daily_public_content", 1)[1]
    assert '("chat_quote", settings.general_chat_id)' not in run_block
    assert '("channel_post", _channel_target(settings))' in run_block
    assert "channel_quote" not in run_block


def test_delivery_keys_are_day_scoped_and_claimed_before_send():
    source = open("app/services/daily_public_content_service.py", encoding="utf-8").read()
    assert 'key=f"era-daily:{kind}:{day}"' in source
    assert 'row.status in {"sent", "claimed", "uncertain"}' in source
    assert source.index("await session.commit()") < source.index("await bot.send_message")


def test_recurring_chat_permission_job_cannot_publish_messages():
    source = open("app/services/chat_permissions_service.py", encoding="utf-8").read()
    # Permission fields such as can_send_messages are expected. Actual Telegram
    # message publication/edit/pin calls are forbidden in this recurring job.
    assert "await bot.send_message(" not in source
    assert "await bot.edit_message" not in source
    assert "await bot.pin_chat_message(" not in source


def test_scheduler_uses_message_free_permission_job_and_daily_content():
    source = open("app/services/system_scheduler.py", encoding="utf-8").read()
    assert "enforce_general_chat_writable" in source
    assert "run_daily_public_content" in source
    assert "ensure_general_chat_writable" not in source
    assert "ensure_general_faq_pinned" not in source
    assert 'id="era-daily-public-content"' in source
    assert 'id="general-chat-faq-pin"' not in source


def test_startup_permission_repair_cannot_use_legacy_publisher():
    source = open("app/webapp.py", encoding="utf-8").read()
    assert "from app.services.chat_permissions_service import enforce_general_chat_writable" in source
    assert "ensure_general_chat_writable" not in source


def test_legacy_morning_evening_general_chat_jobs_are_removed_before_start():
    source = open("app/webapp.py", encoding="utf-8").read()
    assert '"general-content-morning"' in source
    assert '"general-content-evening"' in source
    assert '"general-content-recovery"' in source
    assert "scheduler.remove_job(legacy_job_id)" in source
    assert source.index("scheduler.remove_job(legacy_job_id)") < source.index("scheduler.start()")


def test_startup_pin_refresh_never_creates_registration_promo():
    source = open("app/services/general_chat_menu_service.py", encoding="utf-8").read()
    restore_block = source.split("async def _restore_registration_pin", 1)[1].split("async def _ensure_persistent_navigation", 1)[0]
    assert "send_message" not in restore_block
    assert "pin_chat_message" not in restore_block
    assert "edit_message_text" in restore_block


def test_daily_channel_requires_specific_publication_approval(monkeypatch):
    """A recurring schedule alone must never authorize a new ERA message."""
    import asyncio
    import hashlib
    from datetime import datetime
    from types import SimpleNamespace

    import app.services.daily_public_content_service as daily

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 3, 12, 0, tzinfo=tz)

    monkeypatch.setattr(daily, "datetime", FixedDatetime)
    monkeypatch.setattr(daily, "scheduled_minute", lambda *_: 0)
    sent = []

    async def fake_deliver(*args, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(daily, "_deliver_once", fake_deliver)
    settings = SimpleNamespace(
        era_channel_id="@era_leaders1", era_channel_username="era_leaders1"
    )
    day, target = "2026-11-03", "@era_leaders1"
    content = daily.text_for_day(day, "channel_post")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Neither past successful deliveries nor a configured channel imply consent.
    asyncio.run(daily.run_daily_public_content(object(), settings, None))
    assert sent == []
    assert not daily._has_explicit_channel_approval(day, target, content)

    # Approval is bound to the exact day, channel and text bytes.
    monkeypatch.setattr(
        daily, "APPROVED_CHANNEL_PUBLICATIONS", frozenset({(day, target, digest)})
    )
    assert daily._has_explicit_channel_approval(day, target, content)
    assert not daily._has_explicit_channel_approval("2026-11-04", target, content)
    assert not daily._has_explicit_channel_approval(day, "@other_channel", content)
    assert not daily._has_explicit_channel_approval(day, target, content + "!")

    asyncio.run(daily.run_daily_public_content(object(), settings, None))
    assert len(sent) == 1
    assert sent[0]["text"] == content
    assert sent[0]["chat_id"] == target
