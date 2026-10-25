from pathlib import Path
import unittest

from app.database.career_models import CareerPortfolioItem
from app.database.models import PortfolioItem


ROOT = Path(__file__).resolve().parents[1]


class PortfolioUnificationRegressionTests(unittest.TestCase):
    def test_career_portfolio_is_alias_of_canonical_portfolio(self) -> None:
        self.assertIs(CareerPortfolioItem, PortfolioItem)
        self.assertEqual(CareerPortfolioItem.__tablename__, "portfolio_items")
        for field in (
            "organization",
            "file_name",
            "include_in_resume",
            "submitted_at",
            "verified_at",
        ):
            self.assertTrue(hasattr(PortfolioItem, field), field)

    def test_unification_migration_drops_legacy_table_after_copy(self) -> None:
        migration = (ROOT / "alembic" / "versions" / "0038_unify_portfolio.py").read_text(encoding="utf-8")
        copy_pos = migration.index("INSERT INTO portfolio_items")
        drop_pos = migration.index('op.drop_table("career_portfolio_items")')
        self.assertLess(copy_pos, drop_pos)
        self.assertIn('down_revision = "0037_community_verification"', migration)


if __name__ == "__main__":
    unittest.main()
