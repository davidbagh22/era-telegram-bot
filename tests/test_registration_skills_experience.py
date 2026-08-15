from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.registration import _parse_skills, experience, occupation, skills
from app.states.registration import RegistrationStates
from app.utils import texts


class RegistrationSkillsExperienceTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_skills_splits_deduplicates_and_keeps_natural_text(self) -> None:
        self.assertEqual(
            _parse_skills("SMM, дизайн; Организация мероприятий\nSMM"),
            ["SMM", "дизайн", "Организация мероприятий"],
        )

    async def test_occupation_leads_to_skills_question(self) -> None:
        message = SimpleNamespace(text="Студент и волонтёр", answer=AsyncMock())
        state = AsyncMock()

        await occupation(message, state)

        state.update_data.assert_awaited_once_with(occupation="Студент и волонтёр")
        state.set_state.assert_awaited_once_with(RegistrationStates.skills)
        message.answer.assert_awaited_once_with(texts.REG_SKILLS)

    async def test_skills_are_saved_as_list_then_experience_is_asked(self) -> None:
        message = SimpleNamespace(text="дизайн, тексты, SMM", answer=AsyncMock())
        state = AsyncMock()

        await skills(message, state)

        state.update_data.assert_awaited_once_with(skills=["дизайн", "тексты", "SMM"])
        state.set_state.assert_awaited_once_with(RegistrationStates.experience)
        message.answer.assert_awaited_once_with(texts.REG_EXPERIENCE)

    async def test_experience_is_saved_before_department_selection(self) -> None:
        message = SimpleNamespace(
            text="Организовывал школьные мероприятия и помогал волонтёрской команде",
            answer=AsyncMock(),
        )
        state = AsyncMock()

        await experience(message, state)

        state.update_data.assert_awaited_once_with(
            experience="Организовывал школьные мероприятия и помогал волонтёрской команде"
        )
        state.set_state.assert_awaited_once_with(RegistrationStates.department)
        self.assertEqual(message.answer.await_args.args[0], texts.REG_DEPARTMENT)
        self.assertIsNotNone(message.answer.await_args.kwargs.get("reply_markup"))


if __name__ == "__main__":
    unittest.main()
