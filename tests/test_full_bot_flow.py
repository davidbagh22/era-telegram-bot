from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from app.services.excel_service import build_analytics_workbook


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    file_path = ROOT / path
    if not file_path.exists():
        raise AssertionError(f"Отсутствует обязательный файл: {path}")
    return file_path.read_text(encoding="utf-8")


class FullBotFlowSmokeTests(unittest.TestCase):
    def test_all_critical_modules_exist(self) -> None:
        paths = [
            "app/handlers/registration.py",
            "app/handlers/participant/navigation.py",
            "app/handlers/participant/directions_block7.py",
            "app/handlers/participant/task_block2.py",
            "app/handlers/participant/projects_block5.py",
            "app/handlers/participant/project_event_flow.py",
            "app/handlers/participant/events_stability_block8.py",
            "app/handlers/participant/event_activities_block15.py",
            "app/handlers/participant/partner_offers_block16.py",
            "app/handlers/participant/auction_block17.py",
            "app/handlers/admin/rights_block6.py",
            "app/handlers/admin/task_review_block2.py",
            "app/handlers/admin/projects_block5_decision.py",
            "app/handlers/admin/event_registration_block14.py",
            "app/handlers/admin/event_activities_block15.py",
            "app/handlers/admin/partner_offers_block16.py",
            "app/handlers/admin/auction_block17.py",
            "app/services/event_card.py",
            "app/services/excel_service.py",
        ]
        for path in paths:
            self.assertGreater(len(source(path)), 20, path)

    def test_critical_routers_are_connected(self) -> None:
        participant = source("app/handlers/participant/__init__.py")
        admin = source("app/handlers/admin/__init__.py")
        for marker in (
            "directions_block7.router",
            "task_block2.router",
            "project_event_flow.router",
            "events_stability_block8.router",
            "event_activities_block15.router",
            "partner_offers_block16.router",
            "auction_block17.router",
        ):
            self.assertIn(marker, participant)
        for marker in (
            "rights_block6.router",
            "task_review_block2.router",
            "projects_block5_decision.router",
            "event_registration_block14.router",
            "event_activities_block15.router",
            "partner_offers_block16.router",
            "auction_block17.router",
            "management_ready.router",
        ):
            self.assertIn(marker, admin)

    def test_core_safety_contracts(self) -> None:
        registration = source("app/handlers/registration.py")
        self.assertIn("RegistrationStates.birth_date", registration)
        self.assertIn("photo_file_id", registration)
        self.assertIn("social_url", registration)

        event_card = source("app/services/event_card.py")
        self.assertIn("poster_file_id", event_card)
        self.assertIn("answer_photo", event_card)

        auction_user = source("app/handlers/participant/auction_block17.py")
        auction_admin = source("app/handlers/admin/auction_block17.py")
        self.assertIn("with_for_update", auction_user)
        self.assertIn("Последняя ставка", auction_user)
        self.assertIn("Лидер:", auction_user)
        self.assertIn("Лот передан победителю", auction_admin)

        bind = source("app/handlers/chat_binding.py")
        self.assertIn("_can_bind", bind)
        self.assertIn("Role.ADMIN", bind)

    def test_excel_builds_on_empty_database(self) -> None:
        content = build_analytics_workbook([], [], [], {})
        workbook = load_workbook(BytesIO(content))
        expected = {
            "Сводка",
            "Участники",
            "Департаменты",
            "Направления",
            "Мероприятия",
            "Проекты",
            "Цели месяца",
            "Организации",
        }
        self.assertTrue(expected.issubset(set(workbook.sheetnames)))
        self.assertGreater(len(content), 1000)


if __name__ == "__main__":
    unittest.main()
