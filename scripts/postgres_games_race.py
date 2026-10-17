"""Concurrency acceptance gate for rooms, content reservations and reward caps."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, Message, User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import AppSetting, PointTransaction, User
from app.handlers.era_game_room import _data, _key, _new_room, _recent_game_results, game_callback
from app.services.game_content import items_for_mode
from app.services.game_formats import GameMode
from app.services.game_rewards_service import award_game_points
from app.utils.constants import ApplicationStatus


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('This fixture creates test data: only era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 7_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    format_uid = uid + 1
    async with sessions() as session:
        session.add(User(telegram_id=uid, first_name='CI Games', application_status=ApplicationStatus.APPROVED))
        session.add(User(telegram_id=format_uid, first_name='CI Format', application_status=ApplicationStatus.APPROVED))
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

    async def count_awards(telegram_id):
        async with sessions() as session:
            return int(await session.scalar(
                select(func.count(PointTransaction.id))
                .join(User, User.id == PointTransaction.user_id)
                .where(User.telegram_id == telegram_id, PointTransaction.source_type == 'game')
            ) or 0)

    delivery_bot = SimpleNamespace(edit_message_text=AsyncMock(return_value=True))

    async def answer_worker(answer_data, settings):
        message = Message(message_id=3, date=datetime.now(timezone.utc),
                          chat=Chat(id=format_uid, type='private')).as_(delivery_bot)
        query = SimpleNamespace(
            message=message,
            from_user=TelegramUser(id=format_uid, first_name='CI Format', is_bot=False),
            data=answer_data,
            answer=AsyncMock(),
        )
        async with sessions() as session:
            await game_callback(query, settings, session)

    try:
        rooms = await asyncio.wait_for(asyncio.gather(*(room_worker(uid) for _ in range(8))), 30)
        assert sum(room is not None for room in rooms) == 1, rooms
        another = await room_worker(uid+1)
        # Random packs are personal; verify the actual per-user reservations,
        # without requiring two people to receive an identical first question.
        assert another is not None
        async with sessions() as session:
            for player, room in ((uid, next(room for room in rooms if room)), (uid+1, another)):
                usage = _data(await session.scalar(select(AppSetting).where(
                    AppSetting.key == f'era_game:question_usage:quiz:{player}')))
                assert set(usage) == {str(room['question'])}
        duplicate = await asyncio.wait_for(asyncio.gather(*(award_worker(str(uid)) for _ in range(8))), 30)
        assert sum(duplicate) == 3, duplicate
        capped = await asyncio.wait_for(asyncio.gather(*(award_worker(f'{uid}:{i}') for i in range(12))), 30)
        assert sum(capped) + sum(duplicate) == 20, capped

        settings = SimpleNamespace(feature_games='ALL', feature_tester_ids=[],
                                   general_chat_id=-format_uid, games_rewards_enabled=True, bot_username="ERA_1bot")
        start_message = Message(message_id=2, date=datetime.now(timezone.utc),
                                chat=Chat(id=format_uid, type='private')).as_(delivery_bot)
        start_query = SimpleNamespace(
            message=start_message,
            from_user=TelegramUser(id=format_uid, first_name='CI Format', is_bot=False),
            data='era_game:play:true_or_myth',
            answer=AsyncMock(),
        )
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), \
             patch.object(Message, 'answer', new=AsyncMock(return_value=Message(
                 message_id=20, date=datetime.now(timezone.utc), chat=Chat(id=format_uid, type='private')).as_(delivery_bot))) as send:
            async with sessions() as session:
                await game_callback(start_query, settings, session)
            room_id = f'f{list(GameMode).index(GameMode.TRUE_OR_MYTH)}-{format_uid}'
            room_key = _key(format_uid, None, room_id)
            async with sessions() as session:
                room = _data(await session.scalar(select(AppSetting).where(AppSetting.key == room_key)))
            item = next(item for item in items_for_mode(GameMode.TRUE_OR_MYTH)
                         if item.id == room['item_id'])
            correct = item.challenge.options.index(item.challenge.answer)
            callback_data = f"era_game:format_answer:{room['id']}~{room['token']}:{correct}"
            before = await count_awards(format_uid)
            await asyncio.wait_for(asyncio.gather(*(
                answer_worker(callback_data, settings) for _ in range(8)
            )), 30)
            after = await count_awards(format_uid)
            assert after - before == 1, (before, after)
            assert send.await_count == 1
            assert delivery_bot.edit_message_text.await_count == 1
            async with sessions() as session:
                result = _data(await session.scalar(select(AppSetting).where(AppSetting.key == room_key)))
                assert result['status'] == 'finished' and result['message_id'] == 20
                # Real PostgreSQL JSONB filtering must accept legacy strings and
                # object values, preserve previous rounds and isolate recipients.
                first = await _recent_game_results(session, format_uid)
                assert len(first) == 1 and first[0]['session_token'] == result['session_token']
                session.add(AppSetting(key=f'game-result:history-{uid}', value={
                    'mode': 'solo', 'participants': [format_uid], 'scores': {str(format_uid): 2},
                    'finished_at': datetime.now(timezone.utc).isoformat()}))
                session.add(AppSetting(key=f'game-result:other-{uid}', value=json.dumps({
                    'mode': 'solo', 'participants': [uid], 'scores': {str(uid): 2},
                    'finished_at': datetime.now(timezone.utc).isoformat()})))
                session.add(AppSetting(key=f'game-result:team-{uid}', value={
                    'mode': 'duel', 'participants': [format_uid, uid], 'scores': {str(format_uid): 2},
                    'finished_at': datetime.now(timezone.utc).isoformat()}))
                await session.commit()
                retained = await _recent_game_results(session, format_uid)
                teams = await _recent_game_results(session, format_uid, team=True)
                assert len(retained) == 2 and all(format_uid in item['participants'] for item in retained)
                assert len(teams) == 1 and teams[0]['kind'] == 'duel'
                assert delivery_bot.edit_message_text.await_args.kwargs['text'].count('Баллы ЭРА:') == 1
    finally:
        await engine.dispose()
    print('PostgreSQL games: rooms, player-scoped history, caps, concurrent answer idempotency')


if __name__ == '__main__':
    asyncio.run(main())
