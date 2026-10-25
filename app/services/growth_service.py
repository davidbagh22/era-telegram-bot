from __future__ import annotations

from dataclasses import dataclass

from app.database.models import User
from app.utils.constants import ParticipationStatus

GROWTH_PARTICIPANT = "participant"
GROWTH_ACTIVE = "active"
GROWTH_LEADER = "leader"

GROWTH_LEVEL_ORDER: list[str] = [GROWTH_PARTICIPANT, GROWTH_ACTIVE, GROWTH_LEADER]

GROWTH_LEVEL_LABELS: dict[str, str] = {
    GROWTH_PARTICIPANT: "Участник",
    GROWTH_ACTIVE: "Активный",
    GROWTH_LEADER: "Лидер",
}

# Growth Level (shown on Home) is intentionally distinct from Role, Office,
# Permissions and system role — see docs/ERA_PLATFORM_PROGRESS.md. It is
# computed from the existing, richer participation_status tiers rather than
# a new column, so changing growth criteria is a matter of editing this
# mapping, not a migration. Promotion into "leader" still requires a human
# to move participation_status to PROJECT_CURATOR/COMMUNITY_LEADER via the
# existing admin/leader flows — this module only computes the display tier.
GROWTH_LEVEL_BY_PARTICIPATION_STATUS: dict[str, str] = {
    ParticipationStatus.NEW_MEMBER: GROWTH_PARTICIPANT,
    ParticipationStatus.INVOLVED_MEMBER: GROWTH_PARTICIPANT,
    ParticipationStatus.ACTIVE_MEMBER: GROWTH_ACTIVE,
    ParticipationStatus.TEAM_MEMBER: GROWTH_ACTIVE,
    ParticipationStatus.PROJECT_CURATOR: GROWTH_LEADER,
    ParticipationStatus.COMMUNITY_LEADER: GROWTH_LEADER,
}


@dataclass(frozen=True)
class GrowthProgress:
    level: str
    label: str
    level_index: int
    level_count: int


def growth_level_for(participation_status: str) -> str:
    return GROWTH_LEVEL_BY_PARTICIPATION_STATUS.get(participation_status, GROWTH_PARTICIPANT)


def growth_progress_for(user: User) -> GrowthProgress:
    level = growth_level_for(user.participation_status)
    index = GROWTH_LEVEL_ORDER.index(level)
    return GrowthProgress(
        level=level,
        label=GROWTH_LEVEL_LABELS[level],
        level_index=index,
        level_count=len(GROWTH_LEVEL_ORDER),
    )
