from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class MediaRichEditorContractTests(unittest.TestCase):
    def test_publish_flow_opens_editor_then_patches_before_send(self) -> None:
        api = (FRONTEND / "api" / "media.ts").read_text(encoding="utf-8")
        self.assertIn("openMediaRichEditor", api)
        self.assertIn("await patchMediaContent(contentId, { body: editedBody })", api)
        self.assertLess(
            api.index("await patchMediaContent(contentId, { body: editedBody })"),
            api.index("/publish-now"),
        )

    def test_editor_has_agreed_formatting_and_preview_actions(self) -> None:
        editor = (FRONTEND / "utils" / "mediaRichEditor.ts").read_text(encoding="utf-8")
        for label in ["Жирный", "Курсив", "Ссылка", "Список", "Цитата", "Предпросмотр Telegram", "Сохранить и опубликовать"]:
            self.assertIn(label, editor)
        self.assertIn("sanitizeMediaPreviewHtml", editor)


if __name__ == "__main__":
    unittest.main()
