from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.repositories.users import rating
from app.services.growth_service import growth_progress_for

# Same fetch cap app/handlers/participant/cabinet.py's _rating_context()
# already uses to place a participant even past the visible top slice —
# rating() has no real pagination yet (see its own docstring), so this is
# "fetch effectively everyone" rather than a second page, large enough to
# cover the whole approved, non-blocked membership for the foreseeable
# future.
RATING_FETCH_CAP = 1000
DEFAULT_TOP_LIMIT = 50
MAX_TOP_LIMIT = 100


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    display_name: str
    points: int
    growth_level: str
    is_you: bool


@dataclass(frozen=True)
class LeaderboardSnapshot:
    entries: list[LeaderboardEntry]
    # None only if the viewer isn't in rating() at all (not approved / is
    # blocked) — shouldn't happen in practice since get_current_user
    # already rejects blocked/archived users, but application_status is
    # not itself re-checked here, same as app/api/v1/home.py.
    me: LeaderboardEntry | None


def _display_name(user: User) -> str:
    return f"{user.first_name} {user.last_name or ''}".strip()


def _entry(rank: int, user: User, points: int, viewer_id: int) -> LeaderboardEntry:
    return LeaderboardEntry(
        rank=rank,
        display_name=_display_name(user),
        points=points,
        growth_level=growth_progress_for(user).label,
        is_you=user.id == viewer_id,
    )


async def build_leaderboard(
    session: AsyncSession, viewer: User, *, limit: int = DEFAULT_TOP_LIMIT
) -> LeaderboardSnapshot:
    """Mini App equivalent of the Bot's "🏆 Рейтинг"
    (`cabinet:rating` / `/rating`, app/handlers/participant/cabinet.py) —
    same underlying query (app/repositories/users.py::rating(), already
    scoped to approved, non-blocked participants) and the same fields
    (first/last name + points) it has always shown to any approved
    participant, just surfaced as a Mini App screen instead of a chat
    message. No new privacy surface: docs/DATA_INVENTORY.md section 1
    already classifies first_name/last_name as
    "Обращение к пользователю, отображение в UI, портфолио" — this is
    exactly that, not a new kind of disclosure.
    """
    limit = max(1, min(limit, MAX_TOP_LIMIT))
    rows = await rating(session, limit=RATING_FETCH_CAP)

    entries = [
        _entry(rank, user, points, viewer.id)
        for rank, (user, points) in enumerate(rows[:limit], start=1)
    ]

    me = next(
        (
            _entry(rank, user, points, viewer.id)
            for rank, (user, points) in enumerate(rows, start=1)
            if user.id == viewer.id
        ),
        None,
    )

    return LeaderboardSnapshot(entries=entries, me=me)
