from pathlib import Path
import unittest


class PartnerOffersBlock16Tests(unittest.TestCase):
    def test_participant_flow_contract(self) -> None:
        text = Path("app/handlers/participant/partner_offers_block16.py").read_text(encoding="utf-8")
        for token in (
            'callback_data="offers:list"',
            'callback_data="offers:mine"',
            'F.data.startswith("offer:apply:")',
            "Баллы спишутся только после одобрения",
        ):
            self.assertIn(token, text)

    def test_admin_flow_contract(self) -> None:
        text = Path("app/handlers/admin/partner_offers_block16.py").read_text(encoding="utf-8")
        for token in (
            'F.data == "admin:offers:add"',
            'F.data == "admin:offers:applications"',
            'F.data.startswith("admin:offerapp:approve:")',
            "points=-offer.point_cost",
        ):
            self.assertIn(token, text)

    def test_schema_contract(self) -> None:
        text = Path("app/database/partners.py").read_text(encoding="utf-8")
        self.assertIn("class PartnerOfferApplication", text)
        self.assertIn("point_cost", text)
        self.assertIn("quantity", text)
        self.assertIn("instruction", text)

    def test_migration_contract(self) -> None:
        migration = Path("alembic/versions/0008_partner_offers.py").read_text(encoding="utf-8")
        self.assertIn("partner_offer_applications", migration)
        self.assertIn('down_revision = "0007_merge_current_heads"', migration)


if __name__ == "__main__":
    unittest.main()
