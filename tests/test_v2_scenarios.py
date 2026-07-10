import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect

from app.config import Settings
from app.database import Base
from app.database.models import Auction, RewardItem, Task
from app.keyboards.admin import (
    admin_activity_keyboard,
    admin_communications_keyboard,
    admin_growth_keyboard,
    project_review_actions,
)
from app.keyboards.leader import leader_panel_keyboard
from app.keyboards.participant import (
    journey_keyboard,
    points_hub_keyboard,
    portfolio_keyboard,
    profile_sections_keyboard,
    profile_settings_keyboard,
    rewards_keyboard,
    tasks_keyboard,
)
from app.services.scheduler_service import create_scheduler
from app.utils.constants import BADGES, ROLE_LABELS, Role


def _labels(keyboard) -> list[str]:
    rows = getattr(keyboard, "inline_keyboard", None) or keyboard.keyboard
    return [button.text for row in rows for button in row]


def _callbacks(keyboard) -> set[str]:
    return {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }


class V2ScenarioTests(unittest.TestCase):
    """Ten product journeys that must remain stable as ERA grows."""

    def test_01_user_journey_is_compact_and_grouped(self) -> None:
        labels = _labels(journey_keyboard())
        self.assertEqual(
            labels,
            ["⚙️ Мои данные", "✅ Задачи", "🏆 Баллы", "← Главное меню"],
        )
        points_labels = _labels(points_hub_keyboard())
        self.assertIn("🏅 Достижения и знаки", points_labels)
        profile_labels = _labels(
            profile_sections_keyboard("https://t.me/internal", "https://t.me/external")
        )
        self.assertIn("✏️ Изменить данные", profile_labels)
        self.assertIn("📅 Мероприятия", profile_labels)
        self.assertIn("💡 Проекты", profile_labels)
        self.assertIn("🧩 Направления", profile_labels)
        profile_callbacks = _callbacks(
            profile_sections_keyboard("https://t.me/internal", "https://t.me/external")
        )
        self.assertIn("profile:settings", profile_callbacks)
        self.assertIn("cabinet:events", profile_callbacks)
        self.assertIn("cabinet:projects", profile_callbacks)
        self.assertIn("cabinet:departments", profile_callbacks)
        self.assertNotIn("cabinet:direction:add", profile_callbacks)
        settings_labels = _labels(profile_settings_keyboard())
        for label in (
            "Имя",
            "Фамилия",
            "Дата рождения",
            "Телефон",
            "Email",
            "Город",
            "Учёба / работа",
            "Занятость",
            "Фото",
            "Соцсети",
        ):
            self.assertIn(label, settings_labels)

    def test_02_project_review_has_two_human_stages(self) -> None:
        initial = _callbacks(project_review_actions(7, "initial_review"))
        venue = _callbacks(project_review_actions(7, "venue_review"))
        self.assertIn("admin:project:review:initial_accept:7", initial)
        self.assertIn("admin:project:review:venue_approve:7", venue)
        self.assertIn("admin:project:snooze:7", venue)

    def test_03_admin_activity_has_no_selfie_or_reports(self) -> None:
        labels = " ".join(_labels(admin_activity_keyboard())).lower()
        self.assertNotIn("селфи", labels)
        self.assertNotIn("отчёт", labels)
        self.assertIn("активности после мероприятий", labels)
        self.assertIn("задания и конкурсы", labels)

    def test_04_communications_include_filters_and_greetings_entry(self) -> None:
        labels = _labels(admin_communications_keyboard())
        self.assertIn("Создать рассылку", labels)
        self.assertIn("Приветствия в чатах", labels)
        self.assertNotIn("Рассылки лидеров", labels)

    def test_05_points_economy_exposes_catalogue_and_auctions(self) -> None:
        labels = _labels(admin_growth_keyboard())
        self.assertIn("Каталог возможностей", labels)
        self.assertIn("Аукционы", labels)
        self.assertEqual(len(BADGES), 10)

    def test_06_participant_can_redeem_and_open_auction(self) -> None:
        reward = RewardItem(
            id=1,
            name="Встреча с экспертом",
            description="Разбор идеи",
            point_cost=100,
            created_by=1,
        )
        auction = Auction(
            id=2,
            title="Место в делегации",
            description="Поездка",
            starts_at=datetime.now().astimezone(),
            ends_at=datetime.now().astimezone() + timedelta(days=1),
            created_by=1,
        )
        callbacks = _callbacks(rewards_keyboard([reward], [auction]))
        self.assertIn("reward:view:1", callbacks)
        self.assertIn("auction:view:2", callbacks)

    def test_07_team_task_changes_from_join_to_view(self) -> None:
        task = Task(
            id=9,
            title="Подготовить встречу",
            description="Собрать программу",
            creator_id=1,
            deadline=datetime.now().astimezone() + timedelta(days=3),
        )
        self.assertIn("task:join:9", _callbacks(tasks_keyboard([task], set())))
        self.assertIn("task:view:9", _callbacks(tasks_keyboard([task], {9})))

    def test_08_portfolio_supports_moderation_input_and_pdf_output(self) -> None:
        callbacks = _callbacks(portfolio_keyboard())
        self.assertIn("portfolio:upload", callbacks)
        self.assertIn("portfolio:resume", callbacks)

    def test_09_role_hierarchy_and_leader_scope_are_clear(self) -> None:
        expected = [
            Role.PARTICIPANT,
            Role.ACTIVIST,
            Role.LEADER,
            Role.HEAD,
            Role.COUNCIL,
        ]
        self.assertTrue(all(role in ROLE_LABELS for role in expected))
        labels = " ".join(_labels(leader_panel_keyboard()))
        self.assertIn("Работа в команде", labels)
        self.assertIn("Предложить поощрение", labels)
        self.assertNotIn("Отчёты", labels)

    def test_10_schema_and_background_reminders_cover_v2(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        tables = set(inspect(engine).get_table_names())
        self.assertTrue(
            {
                "chat_greetings",
                "event_activities",
                "task_participants",
                "task_submissions",
                "reward_items",
                "reward_redemptions",
                "auctions",
                "auction_bids",
                "offices",
                "permission_grants",
            }.issubset(tables)
        )
        settings = Settings(bot_token="1234567890:test", admin_ids=[1])
        scheduler = create_scheduler(object(), settings, object())
        job_ids = {job.id for job in scheduler.get_jobs()}
        self.assertIn("event-reminders", job_ids)
        self.assertIn("project-venue-reminders", job_ids)
        self.assertIn("task-reminders", job_ids)


if __name__ == "__main__":
    unittest.main()
