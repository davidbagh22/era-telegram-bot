import unittest
from datetime import date, datetime, timedelta

from app.database.models import Event, RewardItem, Task
from app.services.archive_service import event_is_visible, reward_is_active, task_is_active
from app.utils.constants import EventStatus, TaskStatus


class ArchiveServiceTests(unittest.TestCase):
    def test_past_event_is_not_visible(self) -> None:
        event = Event(
            title="Past",
            description="Past event",
            event_date=date.today() - timedelta(days=1),
            event_time=datetime.now().time(),
            location="ERA",
            format="offline",
            status=EventStatus.PUBLISHED,
            created_by=1,
        )
        self.assertFalse(event_is_visible(event))

    def test_future_event_is_visible(self) -> None:
        event = Event(
            title="Future",
            description="Future event",
            event_date=date.today() + timedelta(days=1),
            event_time=datetime.now().time(),
            location="ERA",
            format="offline",
            status=EventStatus.REGISTRATION_OPEN,
            created_by=1,
        )
        self.assertTrue(event_is_visible(event))

    def test_expired_task_is_not_active(self) -> None:
        task = Task(
            title="Task",
            description="Task",
            creator_id=1,
            deadline=datetime.now().astimezone() - timedelta(hours=1),
            status=TaskStatus.PUBLISHED,
        )
        self.assertFalse(task_is_active(task))

    def test_reward_without_quantity_is_active(self) -> None:
        reward = RewardItem(
            name="Reward",
            description="Reward",
            point_cost=10,
            quantity=None,
            is_active=True,
            created_by=1,
        )
        self.assertTrue(reward_is_active(reward))

    def test_reward_with_zero_quantity_is_not_active(self) -> None:
        reward = RewardItem(
            name="Reward",
            description="Reward",
            point_cost=10,
            quantity=0,
            is_active=True,
            created_by=1,
        )
        self.assertFalse(reward_is_active(reward))


if __name__ == "__main__":
    unittest.main()
