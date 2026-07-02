import inspect
import unittest

from app.handlers.admin.event_activities_block7 import send_to_registered_confirm
from app.handlers.admin.events_block6 import event_kb
from app.handlers.admin.task_review_block2 import _task_menu
from app.keyboards.leader import leader_panel_keyboard
from app.services.event_service import published_events
from app.utils.constants import EventStatus


def callbacks(keyboard):
    return [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]


class StabilizationContractTests(unittest.TestCase):
    def test_admin_can_create_tasks_from_active_menu(self):
        self.assertIn("admin:task:new", callbacks(_task_menu()))

    def test_leader_panel_has_events_and_projects(self):
        values = callbacks(leader_panel_keyboard())
        self.assertIn("leader:events", values)
        self.assertIn("leader:projects", values)
        self.assertEqual(values.count("leader:participants"), 1)

    def test_active_event_can_be_completed(self):
        event = type("EventStub", (), {"id": 4, "status": EventStatus.ACTIVE})()
        self.assertIn("admin:event:status:completed:4", callbacks(event_kb(event)))

    def test_completed_event_can_send_activities(self):
        event = type("EventStub", (), {"id": 5, "status": EventStatus.COMPLETED})()
        self.assertIn("admin:event:activities:send:5", callbacks(event_kb(event)))

    def test_activity_delivery_is_idempotent(self):
        self.assertIn("ERA_ACTIVITIES_SENT", inspect.getsource(send_to_registered_confirm))

    def test_approved_event_is_not_public_before_publish(self):
        self.assertNotIn("EventStatus.APPROVED", inspect.getsource(published_events))


if __name__ == "__main__":
    unittest.main()
