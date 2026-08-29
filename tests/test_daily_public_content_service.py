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


def test_delivery_keys_are_day_scoped_in_source():
    source = open("app/services/daily_public_content_service.py", encoding="utf-8").read()
    assert 'key=f"era-daily:{kind}:{day}"' in source
    assert 'if row and row.status == "sent"' in source


def test_recurring_chat_permission_job_cannot_publish_messages():
    source = open("app/services/chat_permissions_service.py", encoding="utf-8").read()
    assert "send_message" not in source
    assert "edit_message" not in source
    assert "pin_chat_message" not in source


def test_scheduler_uses_message_free_permission_job_and_daily_content():
    source = open("app/services/system_scheduler.py", encoding="utf-8").read()
    assert "enforce_general_chat_writable" in source
    assert "run_daily_public_content" in source
    assert "ensure_general_chat_writable" not in source
