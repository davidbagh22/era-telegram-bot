import re
import unittest

from app.utils import texts


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


if __name__ == "__main__":
    unittest.main()
