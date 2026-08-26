import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy import create_engine, inspect

from app.config import Settings
from app.database import Base, Department, Direction, User
from app.repositories.users import assign_interests, create_user_from_registration
from app.services.ai_service import fallback_project_document
from app.services.project_builder import PROJECT_QUESTIONS, render_project_document
from app.utils.constants import BADGES, DEPARTMENTS, DEFAULT_POINTS


class _ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items


class DomainTests(unittest.TestCase):
    def test_project_builder_has_eighteen_questions_plus_final_preview(self) -> None:
        self.assertEqual(len(PROJECT_QUESTIONS), 18)
        self.assertEqual(
            [question.key for question in PROJECT_QUESTIONS],
            [
                "idea", "title", "problem", "target_audience", "goal", "project_tasks",
                "format", "uniqueness", "scenario", "team", "partners", "resources",
                "budget", "implementation_plan", "promotion", "expected_result",
                "success_metrics", "risks",
            ],
        )
        self.assertTrue(all(question.prompt.strip() for question in PROJECT_QUESTIONS))
        self.assertTrue(all(question.ai_hint is None for question in PROJECT_QUESTIONS))

    def test_project_document_contains_all_constructor_sections(self) -> None:
        document = render_project_document(
            {"title": "Тест", "idea": "Идея"}, "Имя", "@telegram"
        )
        for heading in (
            "1. ИДЕЯ",
            "2. НАЗВАНИЕ",
            "3. ПРОБЛЕМА",
            "4. ЦЕЛЕВАЯ АУДИТОРИЯ",
            "5. ЦЕЛЬ",
            "6. ЗАДАЧИ",
            "7. ФОРМАТ",
            "8. УНИКАЛЬНОСТЬ",
            "9. МЕХАНИКА / ПУТЬ УЧАСТНИКА",
            "10. КОМАНДА",
            "11. ПАРТНЁРЫ",
            "12. РЕСУРСЫ",
            "13. БЮДЖЕТ",
            "14. ПЛАН РЕАЛИЗАЦИИ",
            "15. ПРОДВИЖЕНИЕ",
            "16. РЕЗУЛЬТАТЫ",
            "17. ПОКАЗАТЕЛИ",
            "18. РИСКИ",
            "19. ФИНАЛЬНЫЙ PREVIEW",
        ):
            self.assertIn(heading, document)

    def test_registration_creates_loaded_relationship_collections(self) -> None:
        session = AsyncMock()
        session.add = Mock()
        session.scalar.return_value = None
        data = {
            "first_name": "Тест",
            "last_name": "Участник",
            "age": 20,
            "phone": "+37400000000",
            "city": "Ереван",
            "education_work": "Университет",
            "occupation": "Студент",
            "experience": "Нет",
            "motivation": "Хочу участвовать",
            "available_time": "1–2 часа в неделю",
            "desired_path": "Просто участником",
            "departments": [],
            "directions": [],
        }

        with patch("app.repositories.users.assign_interests", new=AsyncMock()) as assign:
            user, created = asyncio.run(
                create_user_from_registration(
                    session,
                    telegram_id=123,
                    username="test_user",
                    data=data,
                )
            )

        self.assertTrue(created)
        self.assertEqual(user.departments, [])
        self.assertEqual(user.directions, [])
        assign.assert_awaited_once()

    def test_registration_retry_reuses_existing_user(self) -> None:
        existing = User(telegram_id=123, first_name="Тест", departments=[], directions=[])
        session = AsyncMock()
        session.add = Mock()
        session.scalar.return_value = existing
        user, created = asyncio.run(
            create_user_from_registration(session, telegram_id=123, username=None, data={})
        )
        self.assertIs(user, existing)
        self.assertFalse(created)
        session.add.assert_not_called()

    def test_registration_interests_keep_loaded_relationships(self) -> None:
        department = Department(name="Внутренние связи")
        direction = Direction(name="Культура", department=department)
        user = User(telegram_id=1, first_name="Тест", departments=[], directions=[])
        session = AsyncMock()
        session.scalars.side_effect = [_ScalarResult([department]), _ScalarResult([direction])]
        asyncio.run(assign_interests(session, user, [department.name], [direction.name]))
        self.assertIs(user.departments[0].department, department)
        self.assertIs(user.directions[0].direction, direction)

    def test_final_department_structure(self) -> None:
        self.assertEqual(DEPARTMENTS["Внутренние связи"], ("Лидерство", "Культура", "Интерактив"))
        self.assertEqual(DEPARTMENTS["Внешние связи"], ("Международное направление", "Медиа", "Социальные инициативы"))

    def test_reference_data(self) -> None:
        self.assertEqual(len(BADGES), 10)
        self.assertIn("Первый шаг", BADGES)
        self.assertIn("Прорыв месяца", BADGES)
        self.assertEqual(DEFAULT_POINTS["Регистрация в боте"], 5)
        self.assertEqual(DEFAULT_POINTS["Одобренный проект"], 30)

    def test_schema_can_be_created(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        tables = set(inspect(engine).get_table_names())
        self.assertGreaterEqual(len(tables), 22)
        self.assertTrue({"users", "events", "projects", "points", "portfolio_items", "audit_logs", "offices", "permission_grants", "event_activities", "reward_items", "auctions"}.issubset(tables))

    def test_project_fallback_works_without_api_key(self) -> None:
        text = fallback_project_document({"idea": "Культурный квест", "department": "Внутренние связи", "direction": "Культура"})
        self.assertIn("Культурный квест", text)
        self.assertIn("Внутренние связи", text)

    def test_render_postgres_url_is_normalized_for_asyncpg(self) -> None:
        settings = Settings(bot_token="test-token-for-settings", database_url="postgresql://era:secret@host/era")
        self.assertEqual(settings.database_url, "postgresql+asyncpg://era:secret@host/era")

    def test_webhook_secret_is_telegram_safe(self) -> None:
        settings = Settings(bot_token="test-token-for-settings", webhook_secret="unsafe secret with + / = characters")
        self.assertRegex(settings.effective_webhook_secret, r"^[A-Za-z0-9_-]{1,256}$")


if __name__ == "__main__":
    unittest.main()
