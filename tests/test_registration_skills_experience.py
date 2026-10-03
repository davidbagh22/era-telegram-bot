from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.registration import (
    _parse_skills,
    registration_education,
    registration_experience,
    registration_full_name,
)
from app.states.registration import RegistrationStates
from app.utils import texts


class RegistrationSkillsExperienceTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_skills_splits_deduplicates_and_keeps_natural_text(self) -> None:
        self.assertEqual(
            _parse_skills("SMM, дизайн; Организация мероприятий\nSMM"),
            ["SMM", "дизайн", "Организация мероприятий"],
        )

    async def test_full_name_is_collected_in_one_message(self) -> None:
        message = SimpleNamespace(text="Давид Багдасарян", answer=AsyncMock())
        state = AsyncMock()

        await registration_full_name(message, state)

        state.update_data.assert_awaited_once_with(
            first_name="Давид",
            last_name="Багдасарян",
        )
        state.set_state.assert_awaited_once_with(RegistrationStates.age)
        message.answer.assert_awaited_once_with(texts.REG_AGE)

    async def test_education_goes_directly_to_direction_choice(self) -> None:
        message = SimpleNamespace(text="МГУ, студент", answer=AsyncMock())
        state = AsyncMock()

        await registration_education(message, state)

        state.update_data.assert_awaited_once_with(
            education_work="МГУ, студент",
            occupation="МГУ, студент",
            selected_directions=[],
        )
        state.set_state.assert_awaited_once_with(RegistrationStates.directions)
        self.assertEqual(message.answer.await_args.args[0], texts.REG_DIRECTION_SIMPLE)
        self.assertIsNotNone(message.answer.await_args.kwargs.get("reply_markup"))

    async def test_experience_is_one_concrete_free_text_step(self) -> None:
        message = SimpleNamespace(
            text="Организовывал мероприятия и умею делать дизайн",
            answer=AsyncMock(),
        )
        state = AsyncMock()

        await registration_experience(message, state)

        state.update_data.assert_awaited_once_with(
            experience="Организовывал мероприятия и умею делать дизайн",
            skills=[],
        )
        state.set_state.assert_awaited_once_with(RegistrationStates.available_time)
        self.assertEqual(message.answer.await_args.args[0], texts.REG_TIME)


if __name__ == "__main__":
    unittest.main()
