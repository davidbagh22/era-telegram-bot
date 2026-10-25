from __future__ import annotations

import unittest

from app.database.development_models import UserVectorProfile
from app.services.development_service import (
    pick_recommendation,
    public_checkin_answers,
    vector_index,
)


class DummyCheckin:
    def __init__(self, answers_json):
        self.answers_json = answers_json


class AdaptiveDevelopmentTests(unittest.TestCase):
    def test_state_index_never_uses_traits(self) -> None:
        state = {"energy": 50, "agency": 75, "autonomy": 25, "connection": 100, "direction": 50}
        self.assertEqual(vector_index(state), 60)

    def test_private_question_metadata_never_leaks_as_answers(self) -> None:
        row = DummyCheckin({"energy": 3, "_question_codes": ["energy"], "_theme": "Энергия"})
        self.assertEqual(public_checkin_answers(row), {"energy": 3})

    def test_high_responsibility_plus_low_energy_prefers_recovery_not_more_action(self) -> None:
        profile = UserVectorProfile(
            user_id=1,
            traits_json={"big5": {"conscientiousness": 82}},
        )
        tag, _ = pick_recommendation(
            {"energy": 25, "agency": 75, "autonomy": 75, "connection": 75, "direction": 75},
            profile=profile,
        )
        self.assertEqual(tag, "REDUCE_LOAD")

    def test_high_openness_low_follow_through_can_select_finish_one(self) -> None:
        profile = UserVectorProfile(
            user_id=1,
            traits_json={"big5": {"intellect": 82, "conscientiousness": 38}},
        )
        tag, _ = pick_recommendation(
            {"energy": 75, "agency": 75, "autonomy": 75, "connection": 75, "direction": 75},
            profile=profile,
            answers={"finish_visibility": 1},
        )
        self.assertEqual(tag, "FINISH_ONE")

    def test_social_interest_plus_low_first_step_can_select_initiate(self) -> None:
        profile = UserVectorProfile(user_id=1, interests_json={"top_code": ["S", "E"]})
        tag, _ = pick_recommendation(
            {"energy": 75, "agency": 75, "autonomy": 75, "connection": 75, "direction": 75},
            profile=profile,
            answers={"initiative_first": 1},
        )
        self.assertEqual(tag, "INITIATE")

    def test_low_sociality_is_not_automatically_treated_as_a_problem(self) -> None:
        profile = UserVectorProfile(
            user_id=1,
            traits_json={"big5": {"extraversion": 20}, "self_efficacy": 80},
        )
        tag, _ = pick_recommendation(
            {"energy": 75, "agency": 75, "autonomy": 75, "connection": 75, "direction": 75},
            profile=profile,
        )
        self.assertNotIn(tag, {"CONNECT", "INITIATE", "SPEAK_UP"})

    def test_90_day_semantic_cooldown_skips_same_family(self) -> None:
        tag, _ = pick_recommendation(
            {"energy": 25, "agency": 75, "autonomy": 75, "connection": 75, "direction": 75},
            blocked_tags={"RECOVER"},
        )
        self.assertNotEqual(tag, "RECOVER")

    def test_repeated_goal_failure_shrinks_goal(self) -> None:
        tag, _ = pick_recommendation(
            {"energy": 60, "agency": 60, "autonomy": 60, "connection": 60, "direction": 60},
            repeated_goal_failures=3,
        )
        self.assertEqual(tag, "START_SMALL")


if __name__ == "__main__":
    unittest.main()
