from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import event_publication_service as service
from app.services.moscow_house_november import EVENTS


@pytest.mark.asyncio
async def test_event_topic_posts_registration_links_without_duplicate_general_announcement():
    event = SimpleNamespace(id=42, title="Встреча", description="Программа", event_date=date(2026, 11, 23),
                            event_time=time(13), location="Дом Москвы")
    exp = SimpleNamespace(creation_mode="quick", full_description="Программа", chat_url=None,
                          broadcast_targets=["project_topic", "digest_only"], broadcast_enabled=False)
    settings = SimpleNamespace(bot_username="ERA_1bot", general_chat_id=-10012345, general_chat_url="https://t.me/+test")
    with patch.object(service, "event_thread", AsyncMock(return_value=100)), patch.object(
        service, "safe_send_once", AsyncMock(return_value=SimpleNamespace(sent=True))
    ) as send, patch.object(service, "send_general_topic_once", AsyncMock()) as general:
        assert await service.publish_event_announcement(object(), settings, None, event, exp)
        general.assert_not_awaited()
        assert send.await_args.kwargs["message_thread_id"] == 100
        assert exp.chat_url == "https://t.me/c/12345/100"
        assert "startapp=event_42" in send.await_args.args[3]
        assert exp.chat_url in send.await_args.args[3]
    assert [item[0] for item in EVENTS] == [23, 24, 25, 28]
