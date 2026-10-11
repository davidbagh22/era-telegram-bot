"""Concurrency acceptance gate for rooms, content reservations and reward caps."""
import asyncio
import os
import uuid

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import User
from app.handlers.era_game_room import _new_room
from app.services.game_rewards_service import award_game_points
from app.utils.constants import ApplicationStatus


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('This fixture creates test data: only era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 7_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    async with sessions() as session:
        session.add(User(telegram_id=uid, first_name='CI Games', application_status=ApplicationStatus.APPROVED))
        await session.commit()

    async def room_worker(user_id):
        async with sessions() as session:
            room = await _new_room(session, chat_id=-uid, thread_id=1, user_id=user_id, kind='solo')
            await session.commit()
            return room

    async def award_worker(round_id):
        async with sessions() as session:
            amount = await award_game_points(session, telegram_id=uid, round_id=round_id, amount=3)
            await session.commit()
            return amount

    try:
        rooms = await asyncio.wait_for(asyncio.gather(*(room_worker(uid) for _ in range(8))), 30)
        assert sum(room is not None for room in rooms) == 1, rooms
        another = await room_worker(uid+1)
        assert another['question'] != next(room for room in rooms if room)['question']
        duplicate = await asyncio.wait_for(asyncio.gather(*(award_worker(str(uid)) for _ in range(8))), 30)
        assert sum(duplicate) == 3, duplicate
        capped = await asyncio.wait_for(asyncio.gather(*(award_worker(f'{uid}:{i}') for i in range(12))), 30)
        assert sum(capped) + sum(duplicate) == 20, capped
    finally:
        await engine.dispose()
    print('PostgreSQL games: one room, unique questions, one award, daily cap 20')


if __name__ == '__main__':
    asyncio.run(main())
