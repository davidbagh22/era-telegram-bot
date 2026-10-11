"""Close persisted game rooms after downtime without posting empty-lobby notices."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import AppSetting
from app.handlers.era_game_room import _data, _lock, _save


async def expire_game_rooms(session_factory, *, now=None) -> int:
    now = now or datetime.now(timezone.utc)
    async with session_factory() as session:
        keys = (await session.scalars(select(AppSetting.key).where(
            AppSetting.key.like('era_game:%'),
            AppSetting.key != 'era_game:question_usage',
        ))).all()
    closed = 0
    for key in keys:
        # Same room lock order as callbacks; one transaction per room.
        async with session_factory() as session:
            await _lock(session, key)
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
            room = _data(row)
            if room.get('status') not in {'waiting', 'playing'}:
                continue
            if datetime.fromisoformat(room['expires_at']) > now:
                continue
            room['status'] = 'expired'
            await _save(session, key, room)
            await session.commit()
            closed += 1
    return closed
