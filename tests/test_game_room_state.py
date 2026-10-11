import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, Message, User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, PointTransaction, User
from app.handlers.era_game_room import _data, _key, _new_room, _reserve_questions, game_callback, quiz_markup
from app.services.game_rewards_service import award_game_points
from app.services.game_room_expiry_service import expire_game_rooms
from app.utils.constants import ApplicationStatus


class GameFixture:
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test-token', feature_games='TESTERS', feature_tester_ids=[11], games_rewards_enabled=True)
        async with self.sessions() as session:
            user = User(telegram_id=11, first_name='Tester', application_status=ApplicationStatus.APPROVED)
            session.add(user)
            await session.commit()
            self.user_id = user.id

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def new_room(self, kind='solo'):
        async with self.sessions() as session:
            room = await _new_room(session, chat_id=-1001, thread_id=10, user_id=11, kind=kind)
            await session.commit()
            return room

    def query(self, room, choice=0, uid=11, token=None):
        return SimpleNamespace(
            message=Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=-1001,type='supergroup'), message_thread_id=10),
            from_user=TelegramUser(id=uid, first_name='Tester', is_bot=False),
            data=f'era_game:answer:{room["id"]}~{token or room["token"]}:{choice}',
            answer=AsyncMock(),
        )


class QuestionReservationTests(GameFixture, IsolatedAsyncioTestCase):
    async def test_expired_and_invalid_reservations_are_pruned(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=181)).isoformat()
        recent = (now - timedelta(days=1)).isoformat()
        async with self.sessions() as session:
            session.add(AppSetting(key='era_game:question_usage', value=json.dumps({
                '0': old, '1': recent, 'bad': 'not-a-date',
            })))
            await session.commit()
        async with self.sessions() as session:
            chosen = await _reserve_questions(session, now, 1)
            await session.commit()
        assert chosen == [0]
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage'))
            usage = _data(row)
        assert 'bad' not in usage
        assert '1' in usage
        assert '0' in usage


class QuestionHistoryScopeTests(GameFixture, IsolatedAsyncioTestCase):
    async def test_history_is_scoped_to_player_and_format(self):
        async with self.sessions() as session:
            first = await _reserve_questions(
                session, datetime.now(timezone.utc), 1, user_ids=(11,), mode='solo_quiz'
            )
            second = await _reserve_questions(
                session, datetime.now(timezone.utc), 1, user_ids=(11,), mode='solo_quiz'
            )
            another_player = await _reserve_questions(
                session, datetime.now(timezone.utc), 1, user_ids=(99,), mode='solo_quiz'
            )
            another_format = await _reserve_questions(
                session, datetime.now(timezone.utc), 1, user_ids=(11,), mode='culture'
            )
            await session.commit()

        assert first == [0]
        assert second == [1]
        assert another_player == [0]
        assert another_format == [0]

    async def test_team_pack_is_reserved_for_each_player(self):
        async with self.sessions() as session:
            selected = await _reserve_questions(
                session,
                datetime.now(timezone.utc),
                2,
                user_ids=(11, 12),
                mode='team_quiz',
            )
            await session.commit()
        assert selected == [0, 1]
        async with self.sessions() as session:
            for user_id in (11, 12):
                next_pack = await _reserve_questions(
                    session,
                    datetime.now(timezone.utc),
                    1,
                    user_ids=(user_id,),
                    mode='team_quiz',
                )
                assert next_pack == [2]


class GameStateTests(GameFixture, IsolatedAsyncioTestCase):
    async def test_old_round_button_cannot_answer_new_round(self):
        old = await self.new_room()
        await expire_game_rooms(self.sessions, now=datetime.now(timezone.utc)+timedelta(minutes=5))
        current = await self.new_room()
        assert old['token'] != current['token']
        query = self.query(current, token=old['token'])
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)):
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == _key(-1001,10,current['id'])))
            assert _data(row)['answers'] == {}

    async def test_double_answer_awards_only_once_and_nonparticipant_rejected(self):
        room = await self.new_room()
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()) as send:
            async with self.sessions() as session:
                await game_callback(self.query(room, uid=22), self.settings, session)
            async with self.sessions() as session:
                await game_callback(self.query(room), self.settings, session)
            async with self.sessions() as session:
                await game_callback(self.query(room), self.settings, session)
            send.assert_awaited_once()
        async with self.sessions() as session:
            awards = (await session.scalars(select(PointTransaction))).all()
            assert len(awards) == 1 and awards[0].points == 3

    async def test_restart_expiry_closes_waiting_and_playing_only_once(self):
        await self.new_room()
        await self.new_room('team')
        now = datetime.now(timezone.utc)
        assert await expire_game_rooms(self.sessions, now=now) == 0
        assert await expire_game_rooms(self.sessions, now=now+timedelta(minutes=5)) == 2
        assert await expire_game_rooms(self.sessions, now=now+timedelta(minutes=6)) == 0

    async def test_award_caps_use_yerevan_midnight_and_shared_ledger(self):
        now = datetime(2026,10,11,20,5,tzinfo=timezone.utc)  # Oct 12 locally
        async with self.sessions() as session:
            session.add_all([
                PointTransaction(user_id=self.user_id, points=20, reason='yesterday', source_type='game', created_at=now-timedelta(minutes=10)),
                PointTransaction(user_id=self.user_id, points=18, reason='today', source_type='game', created_at=now-timedelta(minutes=1)),
                PointTransaction(user_id=self.user_id, points=100, reason='volunteer', source_type='task', created_at=now),
            ])
            await session.flush()
            assert await award_game_points(session, telegram_id=11, round_id='cap', amount=3, now=now) == 2
            assert await award_game_points(session, telegram_id=11, round_id='cap', amount=3, now=now) == 0
            assert await award_game_points(session, telegram_id=11, round_id='cap-next', amount=3, now=now) == 0
            assert await award_game_points(session, telegram_id=99, round_id='absent', amount=3, now=now) == 0
            await session.commit()

    async def test_weekly_and_monthly_limits(self):
        now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        async with self.sessions() as session:
            session.add(PointTransaction(user_id=self.user_id, points=100, reason='weekly', source_type='game', created_at=now-timedelta(days=1)))
            await session.flush()
            assert await award_game_points(session, telegram_id=11, round_id='week', amount=3, now=now) == 0
            session.add(PointTransaction(user_id=self.user_id, points=200, reason='month', source_type='game', created_at=now-timedelta(days=8)))
            await session.flush()
            assert await award_game_points(session, telegram_id=11, round_id='month', amount=3, now=now+timedelta(days=7)) == 0

    async def test_duplicate_lobby_join_does_not_start_round(self):
        room = await self.new_room('team')
        query = self.query(room, uid=11)
        query.data = f"era_game:join:{room['id']}~{room['token']}"
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=AsyncMock()
        ) as send:
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
            send.assert_not_awaited()
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == _key(-1001, 10, room['id'])))
            state = _data(row)
            assert state['status'] == 'waiting'
            assert state['participants'] == [11]
            assert state['question'] is None

    async def test_full_lobby_rejects_new_member_without_mutation(self):
        room = await self.new_room('team')
        key = _key(-1001, 10, room['id'])
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
            data = _data(row)
            data['participants'] = list(range(11, 19))
            row.value = json.dumps(data)
            await session.commit()
        query = self.query(room, uid=99)
        query.data = f"era_game:join:{room['id']}~{room['token']}"
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)):
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        query.answer.assert_awaited()
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
            assert _data(row)['participants'] == list(range(11, 19))

    async def test_abandoned_lobby_does_not_consume_content(self):
        await self.new_room('team')
        async with self.sessions() as session:
            usage = await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage'))
            assert usage is None

    async def test_question_exhaustion_never_silently_repeats(self):
        from app.handlers.era_game_room import QUESTIONS
        async with self.sessions() as session:
            session.add(AppSetting(key='era_game:question_usage:solo_quiz:11', value=json.dumps({str(i):datetime.now(timezone.utc).isoformat() for i in range(len(QUESTIONS))})))
            await session.commit()
        assert (await self.new_room())['status'] == 'exhausted'


def test_round_callbacks_fit_telegram_limit():
    for row in quiz_markup('solo-999999999999~abcdef123456', ('One','Two')).inline_keyboard:
        assert len(row[0].callback_data.encode()) <= 64


class MultiRoundGamesTests(GameFixture, IsolatedAsyncioTestCase):
    async def current_room(self, room_id):
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == _key(-1001, 10, room_id)))
            return _data(row)

    async def test_five_questions_award_only_after_completion_and_reject_old_button(self):
        from app.handlers.era_game_room import QUESTIONS
        async with self.sessions() as session:
            room = await _new_room(session, chat_id=-1001, thread_id=10, user_id=11, kind='solo', questions_per_game=5)
            await session.commit()
        old = dict(room)
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            for position in range(5):
                query = self.query(room, choice=QUESTIONS[room['question']][2])
                async with self.sessions() as session:
                    await game_callback(query, self.settings, session)
                room = await self.current_room(room['id'])
                async with self.sessions() as session:
                    awards = (await session.scalars(select(PointTransaction))).all()
                    assert len(awards) == (1 if position == 4 else 0)
                if position == 0:
                    async with self.sessions() as session:
                        await game_callback(self.query(old), self.settings, session)
                    assert (await self.current_room(room['id']))['answers'] == {}
            assert room['status'] == 'finished'
            assert room['scores'] == {'11': 5}
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
                assert len((await session.scalars(select(PointTransaction))).all()) == 1

    async def test_incomplete_or_low_score_quiz_has_no_reward(self):
        from app.handlers.era_game_room import QUESTIONS
        async with self.sessions() as session:
            room = await _new_room(session, chat_id=-1001, thread_id=10, user_id=11, kind='solo', questions_per_game=5)
            await session.commit()
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            for position in range(5):
                correct = QUESTIONS[room['question']][2]
                choice = correct if position < 2 else (correct+1) % 3
                async with self.sessions() as session:
                    await game_callback(self.query(room, choice=choice), self.settings, session)
                room = await self.current_room(room['id'])
            assert room['scores'] == {'11': 2}
            assert room['status'] == 'finished'
        async with self.sessions() as session:
            assert (await session.scalars(select(PointTransaction))).all() == []

    async def test_ready_check_requires_two_explicit_confirmations(self):
        room = await self.new_room('team')
        async def click(operation, uid):
            query = self.query(room, uid=uid)
            query.data = f"era_game:{operation}:{room['id']}~{room['token']}"
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            await click('join', 22)
            assert (await self.current_room('team'))['status'] == 'ready_check'
            await click('ready', 99)
            await click('ready', 11)
            await click('ready', 11)
            state = await self.current_room('team')
            assert state['ready'] == [11] and state['question'] is None
            await click('ready', 22)
            state = await self.current_room('team')
            assert state['status'] == 'playing' and state['participants'] == [11,22]

    async def test_insufficient_pack_does_not_reserve_partial_content(self):
        from app.handlers.era_game_room import QUESTIONS, _reserve_questions
        used = {str(i): datetime.now(timezone.utc).isoformat() for i in range(len(QUESTIONS)-4)}
        async with self.sessions() as session:
            session.add(AppSetting(key='era_game:question_usage', value=json.dumps(used)))
            await session.commit()
        async with self.sessions() as session:
            assert await _reserve_questions(session, datetime.now(timezone.utc), 5) == []
            row = await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage'))
            assert _data(row) == used


    async def test_resume_does_not_advance_or_consume_content(self):
        room = await self.new_room()
        query = self.query(room)
        query.data = 'era_game:resume'
        async with self.sessions() as session:
            usage_before = _data(await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage')))
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()) as send:
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
            send.assert_awaited_once()
        assert await self.current_room(room['id']) == room
        async with self.sessions() as session:
            assert _data(await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage'))) == usage_before
            assert (await session.scalars(select(PointTransaction))).all() == []

    async def test_ready_check_expires_without_consuming_content_or_rewards(self):
        room = await self.new_room('team')
        query = self.query(room, uid=22)
        query.data = f"era_game:join:{room['id']}~{room['token']}"
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        assert (await self.current_room('team'))['status'] == 'ready_check'
        assert await expire_game_rooms(self.sessions, now=datetime.now(timezone.utc)+timedelta(seconds=30)) == 1
        assert (await self.current_room('team'))['status'] == 'expired'
        async with self.sessions() as session:
            assert await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage')) is None
            assert (await session.scalars(select(PointTransaction))).all() == []

    async def test_team_unique_winner_bonus_and_duplicate_final_callback(self):
        from app.handlers.era_game_room import QUESTIONS
        async with self.sessions() as session:
            session.add(User(telegram_id=22, first_name='Second', application_status=ApplicationStatus.APPROVED))
            room = await _new_room(session, chat_id=-1001, thread_id=10, user_id=11, kind='team', questions_per_game=5)
            await session.commit()
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            for operation, uid in [('join', 22), ('ready', 11), ('ready', 22)]:
                query = self.query(room, uid=uid)
                query.data = f"era_game:{operation}:{room['id']}~{room['token']}"
                async with self.sessions() as session:
                    await game_callback(query, self.settings, session)
            room = await self.current_room('team')
            for position in range(5):
                correct = QUESTIONS[room['question']][2]
                for uid in (11, 22):
                    choice = correct if uid == 11 or position < 3 else (correct+1) % 3
                    query = self.query(room, uid=uid, choice=choice)
                    async with self.sessions() as session:
                        await game_callback(query, self.settings, session)
                room = await self.current_room('team')
            assert room['scores'] == {'11': 5, '22': 3}
            assert room['status'] == 'finished'
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        async with self.sessions() as session:
            awards = (await session.execute(select(User.telegram_id, PointTransaction.points).join(PointTransaction, PointTransaction.user_id == User.id))).all()
            assert sorted(awards) == [(11, 5), (22, 3)]


    async def test_team_waits_for_all_three_joined_players(self):
        room = await self.new_room('team')
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            for operation, uid in [('join', 22), ('join', 33), ('ready', 11), ('ready', 22)]:
                query = self.query(room, uid=uid)
                query.data = f"era_game:{operation}:{room['id']}~{room['token']}"
                async with self.sessions() as session:
                    await game_callback(query, self.settings, session)
            state = await self.current_room('team')
            assert state['status'] == 'ready_check' and state['question'] is None
            query = self.query(room, uid=33)
            query.data = f"era_game:ready:{room['id']}~{room['token']}"
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
            state = await self.current_room('team')
            assert state['status'] == 'playing' and state['participants'] == [11, 22, 33]


    async def test_roster_change_cannot_strand_ready_players(self):
        room = await self.new_room('team')
        async def click(operation, uid):
            query = self.query(room, uid=uid)
            query.data = f"era_game:{operation}:{room['id']}~{room['token']}"
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=AsyncMock()):
            for operation, uid in [('join', 22), ('join', 33), ('ready', 11), ('ready', 22)]:
                await click(operation, uid)
            before = await self.current_room('team')
            await click('leave', 99)
            assert await self.current_room('team') == before
            await click('leave', 33)
            state = await self.current_room('team')
            assert state['ready'] == [] and state['participants'] == [11, 22]
            await click('ready', 11)
            await click('ready', 22)
            assert (await self.current_room('team'))['status'] == 'playing'
