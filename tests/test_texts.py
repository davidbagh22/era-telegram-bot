import re
import unittest

from app.utils import texts


# Phrases that read like generic AI/marketing templates in bot copy.
_AI_TEMPLATE_FRAGMENTS = (
    "не просто чат",
    "не просто анкету",
    "история роста",
    "становится заметной миру",
    "внутреннюю силу",
    "не про соревнование ради цифр",
    "ЭРА строится не документами",
    "Лидер в ЭРА — это не статус",
    "среда, где молодёжь растёт",
)


class TextStyleTests(unittest.TestCase):
    def test_static_user_texts_do_not_use_informal_address(self) -> None:
        forbidden = re.compile(
            r"(?i)(?<![а-яё])(ты|тебе|тебя|твой|твоя|твои|выбери|напиши свою)(?![а-яё])"
        )
        offenders = []
        for name, value in vars(texts).items():
            if name.startswith("_") or not isinstance(value, str):
                continue
            if forbidden.search(value):
                offenders.append(name)
        self.assertEqual(offenders, [])

    def test_required_copy_is_present(self) -> None:
        self.assertIn("Подпишитесь на канал", texts.SUBSCRIPTION_REQUIRED)
        self.assertIn("Ваш путь", texts.SUBSCRIPTION_CONFIRMED)
        self.assertIn("Социальные инициативы", texts.EXTERNAL_DEPARTMENT)

    def test_bot_copy_avoids_ai_template_fragments(self) -> None:
        offenders: list[str] = []
        for name, value in vars(texts).items():
            if name.startswith("_") or not isinstance(value, str):
                continue
            lowered = value.lower()
            for fragment in _AI_TEMPLATE_FRAGMENTS:
                if fragment.lower() in lowered:
                    offenders.append(f"{name}:{fragment}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
