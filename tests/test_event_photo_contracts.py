from __future__ import annotations

import inspect
import unittest

from app.handlers.admin import events_block6
from app.handlers.participant import project_event_photo_flow
from app.services import event_card


class EventPosterContractTests(unittest.TestCase):
    def test_event_card_helper_uses_photo_with_fallback(self) -> None:
        source = inspect.getsource(event_card.send_event_card)
        self.assertIn("answer_photo", source)
        self.assertIn("poster_file_id", source)
        self.assertIn("await target.answer(text", source)

    def test_event_card_to_chat_uses_send_photo(self) -> None:
        source = inspect.getsource(event_card.send_event_card_to_chat)
        self.assertIn("safe_send_photo", source)
        self.assertIn("safe_send", source)

    def test_project_event_flow_saves_project_id_and_poster(self) -> None:
        source = inspect.getsource(project_event_photo_flow.project_event_confirm)
        self.assertIn("project_id=project.id", source)
        self.assertIn("poster_file_id=data.get", source)
        self.assertIn("EventStatus.PENDING_APPROVAL", source)

    def test_admin_event_cards_use_photo_helper(self) -> None:
        self.assertIn("send_event_card", inspect.getsource(events_block6.events_list))
        self.assertIn("send_event_card", inspect.getsource(events_block6.broadcast_preview))
        # Legacy broadcast now uses the durable photo-capable topic transport.
        self.assertIn("_deliver_prepared_announcement", inspect.getsource(events_block6.broadcast_publish))
        delivery_source = inspect.getsource(events_block6._deliver_prepared_announcement)
        self.assertIn("send_general_topic_once", delivery_source)
        self.assertIn("photo=poster if index == 0 else None", delivery_source)



if __name__ == "__main__":
    unittest.main()
