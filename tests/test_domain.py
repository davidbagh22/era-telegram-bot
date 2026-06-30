import unittest

from sqlalchemy import create_engine, inspect

from app.config import Settings
from app.database import Base
from app.services.ai_service import fallback_project_document
from app.utils.constants import BADGES, DEPARTMENTS, DEFAULT_POINTS


class DomainTests(unittest.TestCase):
    def test_final_department_structure(self) -> None:
        self.assertEqual(
            DEPARTMENTS["Внутренние связи"],
            ("Лидерство", "Культура", "Интерактив"),
        )
        self.assertEqual(
            DEPARTMENTS["Внешние связи"],
            ("Международное направление", "Медиа", "Социальные инициативы"),
        )

    def test_reference_data(self) -> None:
        self.assertIn("Лидер месяца", BADGES)
        self.assertEqual(DEFAULT_POINTS["Регистрация в боте"], 5)
        self.assertEqual(DEFAULT_POINTS["Одобренный проект"], 30)

    def test_schema_can_be_created(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        tables = set(inspect(engine).get_table_names())
        self.assertGreaterEqual(len(tables), 22)
        self.assertTrue(
            {
                "users",
                "events",
                "projects",
                "points",
                "portfolio_items",
                "audit_logs",
            }.issubset(tables)
        )

    def test_project_fallback_works_without_api_key(self) -> None:
        text = fallback_project_document(
            {
                "idea": "Культурный квест",
                "department": "Внутренние связи",
                "direction": "Культура",
            }
        )
        self.assertIn("Культурный квест", text)
        self.assertIn("Внутренние связи", text)

    def test_render_postgres_url_is_normalized_for_asyncpg(self) -> None:
        settings = Settings(
            bot_token="test-token-for-settings",
            database_url="postgresql://era:secret@host/era",
        )
        self.assertEqual(
            settings.database_url,
            "postgresql+asyncpg://era:secret@host/era",
        )


if __name__ == "__main__":
    unittest.main()
