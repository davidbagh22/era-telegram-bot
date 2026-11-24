"""Admin-facing cards must show Russian status labels, not raw enums."""
from types import SimpleNamespace
from unittest import TestCase

from app.handlers.admin.auction_block17 import AUCTION_STATUS_LABELS, auctions_keyboard


class AdminStatusLabelsPolishTests(TestCase):
    def test_auction_keyboard_uses_russian_status(self):
        auctions = [
            SimpleNamespace(id=1, title="Сертификат", status="active"),
            SimpleNamespace(id=2, title="Мерч", status="completed"),
            SimpleNamespace(id=3, title="Неизвестный", status="weird"),
        ]
        labels = [button.text for row in auctions_keyboard(auctions).inline_keyboard for button in row]
        self.assertTrue(any("идут ставки" in text for text in labels))
        self.assertTrue(any("победитель подтверждён" in text for text in labels))
        self.assertTrue(any("статус уточняется" in text for text in labels))
        self.assertFalse(any(" active" in text or text.endswith("active") for text in labels))
        self.assertEqual(AUCTION_STATUS_LABELS["delivered"], "лот передан")

    def test_literature_delivery_labels_cover_known_statuses(self):
        source = open("app/handlers/admin/literature_editor.py", encoding="utf-8").read()
        self.assertIn("'sent': 'доставлена'", source)
        self.assertIn("delivery_labels.get(receipt.status, \"статус уточняется\")", source)
        self.assertNotIn("Доставка: {receipt.status}", source)
