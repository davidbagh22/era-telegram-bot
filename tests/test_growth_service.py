from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.growth_service import (
    GROWTH_ACTIVE,
    GROWTH_LEADER,
    GROWTH_PARTICIPANT,
    growth_level_for,
    growth_progress_for,
)
from app.utils.constants import ParticipationStatus


class GrowthLevelForTests(unittest.TestCase):
    def test_new_and_involved_member_are_participant(self) -> None:
        self.assertEqual(growth_level_for(ParticipationStatus.NEW_MEMBER), GROWTH_PARTICIPANT)
        self.assertEqual(
            growth_level_for(ParticipationStatus.INVOLVED_MEMBER), GROWTH_PARTICIPANT
        )

    def test_active_and_team_member_are_active(self) -> None:
        self.assertEqual(growth_level_for(ParticipationStatus.ACTIVE_MEMBER), GROWTH_ACTIVE)
        self.assertEqual(growth_level_for(ParticipationStatus.TEAM_MEMBER), GROWTH_ACTIVE)

    def test_curator_and_community_leader_are_leader(self) -> None:
        self.assertEqual(growth_level_for(ParticipationStatus.PROJECT_CURATOR), GROWTH_LEADER)
        self.assertEqual(
            growth_level_for(ParticipationStatus.COMMUNITY_LEADER), GROWTH_LEADER
        )

    def test_unknown_status_falls_back_to_participant(self) -> None:
        self.assertEqual(growth_level_for("something_unmapped"), GROWTH_PARTICIPANT)


class GrowthProgressForTests(unittest.TestCase):
    def test_progress_reports_index_and_count(self) -> None:
        user = SimpleNamespace(participation_status=ParticipationStatus.ACTIVE_MEMBER)
        progress = growth_progress_for(user)
        self.assertEqual(progress.level, GROWTH_ACTIVE)
        self.assertEqual(progress.label, "Активный")
        self.assertEqual(progress.level_index, 1)
        self.assertEqual(progress.level_count, 3)

    def test_leader_is_last_index(self) -> None:
        user = SimpleNamespace(participation_status=ParticipationStatus.COMMUNITY_LEADER)
        progress = growth_progress_for(user)
        self.assertEqual(progress.level_index, 2)


if __name__ == "__main__":
    unittest.main()
