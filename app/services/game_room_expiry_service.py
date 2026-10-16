"""Close persisted game rooms after downtime without posting empty-lobby notices."""
from datetime import datetime, timezone

from sqlalchemy import select
from aiogram.types import Chat, Message

from app.database.models import AppSetting
from app.handlers.era_game_room import _data, _lock, _save, _publish_room


async def expire_game_rooms(session_factory, bot=None, *, now=None) -> int:
    now = now or datetime.now(timezone.utc)
    async with session_factory() as session:
        keys = (await session.scalars(select(AppSetting.key).where(
            AppSetting.key.like('era_game:%'),
            AppSetting.key.not_like('era_game:question_usage%'),
            AppSetting.key.not_like('era_game:content_usage:%'),
        ))).all()
    closed = 0
    for key in keys:
        # Same room lock order as callbacks; one transaction per room.
        async with session_factory() as session:
            await _lock(session, key)
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
            room = _data(row)
            if room.get('status') not in {'waiting', 'ready_check', 'playing'}:
                if bot is not None and room.get('message_id') and room.get('status') in {'expired', 'finished', 'cancelled', 'exhausted'} and room.get('card_status') != room.get('status'):
                    parts = key.split(':')
                    chat_id, thread = int(parts[1]), parts[2]
                    message = Message(message_id=room['message_id'], date=now,
                                      chat=Chat(id=chat_id, type='private' if chat_id > 0 else 'supergroup'),
                                      message_thread_id=int(thread) if thread != 'None' else None).as_(bot)
                    await _publish_room(session, key, message)
                continue
            if datetime.fromisoformat(room['expires_at']) > now:
                continue
            room['status'] = 'expired'
            await _save(session, key, room)
            await session.commit()
            closed += 1
            if bot is not None and room.get('message_id'):
                parts = key.split(':')
                chat_id, thread = int(parts[1]), parts[2]
                message = Message(message_id=room['message_id'], date=now,
                                  chat=Chat(id=chat_id, type='private' if chat_id > 0 else 'supergroup'),
                                  message_thread_id=int(thread) if thread != 'None' else None).as_(bot)
                await _publish_room(session, key, message)
    return closed
