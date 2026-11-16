"""Human media-task titles replace formulaic «Медиа · …» generators."""

from __future__ import annotations

import unittest

from app.services.media_service import media_task_display_title, rewrite_formulaic_media_title


class MediaTaskTitleTests(unittest.TestCase):
    def test_new_titles_are_human(self) -> None:
        self.assertEqual(
            media_task_display_title("text", "События ЭРА"),
            "Написать текст для «События ЭРА»",
        )
        self.assertEqual(
            media_task_display_title("photo", None),
            "Сделать фото для «публикации ЭРА»",
        )

    def test_rewrites_only_formulaic_titles(self) -> None:
        self.assertEqual(
            rewrite_formulaic_media_title("Медиа · Текст · События ЭРА"),
            "Написать текст для «События ЭРА»",
        )
        self.assertIsNone(rewrite_formulaic_media_title("Сними короткое видео об ЭРА"))
        self.assertIsNone(rewrite_formulaic_media_title("Свой авторский заголовок"))
