import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

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
        self.bot = Mock()
        self.bot.edit_message_text = AsyncMock(return_value=True)
        sent = Message(message_id=66, date=datetime.now(timezone.utc), chat=Chat(id=-1001, type='supergroup'), message_thread_id=10).as_(self.bot)
        self.send = AsyncMock(return_value=sent)
        self.settings = Settings(bot_token='1234567890:test-token', feature_games='TESTERS', feature_tester_ids=[11], games_rewards_enabled=True)
        async with self.sessions() as session:
            user = User(telegram_id=11, first_name='Tester', application_status=ApplicationStatus.APPROVED)
            session.add(user)
            session.add_all(User(telegram_id=uid, first_name=f'Player {uid}', application_status=ApplicationStatus.APPROVED) for uid in (12, 22, 33))
            await session.commit()
            self.user_id = user.id

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def new_room(self, kind='solo'):
        async with self.sessions() as session:
            room = await _new_room(session, chat_id=-1001, thread_id=10, user_id=11, kind=kind)
            await session.commit()
            return room

    def query(self, room, choice=None, uid=11, token=None):
        if choice is None:
            from app.handlers.era_game_room import QUESTIONS
            choice = QUESTIONS[room['question']][2] if isinstance(room.get('question'), int) else 0
        return SimpleNamespace(
            message=Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=-1001,type='supergroup'), message_thread_id=10).as_(self.bot),
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
    async def test_history_is_personal_and_quiz_formats_share_seen_questions(self):
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
                session, datetime.now(timezone.utc), 1, user_ids=(11,), mode='team_duel'
            )
            await session.commit()

        assert len(first) == len(second) == len(another_player) == len(another_format) == 1
        assert len(set(first + second + another_format)) == 3
        async with self.sessions() as session:
            own_usage = _data(await session.scalar(select(AppSetting).where(
                AppSetting.key == 'era_game:question_usage:quiz:99')))
        assert set(own_usage) == {str(another_player[0])}

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
        assert len(selected) == len(set(selected)) == 2
        async with self.sessions() as session:
            for user_id in (11, 12):
                next_pack = await _reserve_questions(
                    session,
                    datetime.now(timezone.utc),
                    1,
                    user_ids=(user_id,),
                    mode='team_quiz',
                )
                assert len(next_pack) == 1 and not set(next_pack).intersection(selected)


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
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send) as send:
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

    async def test_blocked_archived_and_unapproved_profiles_receive_no_rewards(self):
        async with self.sessions() as session:
            user = await session.get(User, self.user_id)
            for attribute, value in (("is_blocked", True), ("is_archived", True),
                                     ("application_status", ApplicationStatus.PENDING)):
                old = getattr(user, attribute)
                setattr(user, attribute, value)
                await session.flush()
                assert await award_game_points(session, telegram_id=11, round_id=attribute, amount=3) == 0
                setattr(user, attribute, old)
            await session.commit()

    async def test_blocked_profile_cannot_change_a_game_room(self):
        room = await self.new_room()
        query = self.query(room)
        with patch("app.handlers.era_game_room._allowed", new=AsyncMock(return_value=True)) as allowed:
            async with self.sessions() as session:
                user = await session.get(User, self.user_id)
                user.is_blocked = True
                await game_callback(query, self.settings, session, user=user)
            allowed.assert_not_awaited()
        query.answer.assert_awaited_once()
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == _key(-1001, 10, room["id"])))
            assert _data(row).get("answers", {}) == {}

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
            Message, 'answer', new=self.send
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
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
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
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
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
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
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
        # Shared resume restores a team; solo recovery is tested privately.
        room = await self.new_room('team')
        query = self.query(room, choice=0)
        query.data = 'era_game:resume'
        async with self.sessions() as session:
            usage_before = _data(await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage')))
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send) as send:
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
            send.assert_awaited_once()
        current = await self.current_room(room['id'])
        assert all(current[k] == v for k, v in room.items())
        assert current['message_id'] == 66
        async with self.sessions() as session:
            assert _data(await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage'))) == usage_before
            assert (await session.scalars(select(PointTransaction))).all() == []

    async def test_ready_check_expires_without_consuming_content_or_rewards(self):
        room = await self.new_room('team')
        query = self.query(room, uid=22)
        query.data = f"era_game:join:{room['id']}~{room['token']}"
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        assert (await self.current_room('team'))['status'] == 'ready_check'
        assert await expire_game_rooms(self.sessions, now=datetime.now(timezone.utc)+timedelta(seconds=100)) == 1
        assert (await self.current_room('team'))['status'] == 'expired'
        async with self.sessions() as session:
            assert await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage')) is None
            assert (await session.scalars(select(PointTransaction))).all() == []

    async def test_team_unique_winner_bonus_and_duplicate_final_callback(self):
        from app.handlers.era_game_room import QUESTIONS
        async with self.sessions() as session:
            room = await _new_room(session, chat_id=-1001, thread_id=10, user_id=11, kind='team', questions_per_game=5)
            await session.commit()
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
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
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
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
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
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


class AdditionalFormatHandlerTests(GameFixture, IsolatedAsyncioTestCase):
    async def _format_room(self):
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key.like('era_game:11:None:f%')))
            return _data(row)

    def query_data(self, data, uid=11):
        query = self.query({"id": "unused", "token": "unused"}, uid=uid)
        query.data = data
        if data == 'era_game:solo' or data.startswith(('era_game:play:', 'era_game:format_answer:', 'era_game:hint:')):
            query.message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=uid, type='private'), from_user=query.from_user).as_(self.bot)
        return query

    async def test_binary_format_is_playable_idempotent_and_explains(self):
        start = self.query_data('era_game:play:true_or_myth')
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=self.send
        ) as send:
            async with self.sessions() as session:
                await game_callback(start, self.settings, session)
            room = await self._format_room()
            reference = room['id'] + '~' + room['token']
            from app.handlers.era_game_room import _format_item
            item = _format_item(room)
            correct = item.challenge.options.index(item.challenge.answer)
            answer = self.query_data(f'era_game:format_answer:{reference}:{correct}')
            async with self.sessions() as session:
                await game_callback(answer, self.settings, session)
            async with self.sessions() as session:
                await game_callback(answer, self.settings, session)
            assert send.await_count == 1
            self.bot.edit_message_text.assert_awaited()
        room = await self._format_room()
        assert room['status'] == 'finished'
        assert room['scores']['11'] == 1
        async with self.sessions() as session:
            rewards = (await session.scalars(select(PointTransaction))).all()
        assert len(rewards) == 1

    async def test_each_single_player_format_completes_through_telegram_callback(self):
        from app.services.game_content import items_for_mode
        from app.services.game_formats import GameMode, check_answer

        modes = (
            GameMode.TRUE_OR_MYTH, GameMode.GUESS_COUNTRY, GameMode.CHRONOLOGY,
            GameMode.WORD_CHAIN, GameMode.ASSOCIATIONS, GameMode.LOGIC,
            GameMode.CULTURE, GameMode.MEMORY,
        )
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=self.send
        ):
            for mode in modes:
                start = self.query_data(f'era_game:play:{mode.value}')
                async with self.sessions() as session:
                    await game_callback(start, self.settings, session)
                room = await self._format_room()
                item = next(item for item in items_for_mode(mode) if item.id == room['item_id'])
                correct = next(
                    index for index, option in enumerate(item.challenge.options)
                    if check_answer(item.challenge, option, previous_word=item.previous_word)
                )
                answer = self.query_data(
                    f"era_game:format_answer:{room['id']}~{room['token']}:{correct}"
                )
                async with self.sessions() as session:
                    await game_callback(answer, self.settings, session)
                room = await self._format_room()
                assert room['status'] == 'finished', mode
                assert room['scores']['11'] > 0, mode
                # This fixture has one game mode per test run; delete state so
                # the helper selects the next player's room on the next loop.
                if mode != modes[-1]:
                    async with self.sessions() as session:
                        state = await session.scalar(select(AppSetting).where(
                            AppSetting.key == _key(11, None, room['id'])
                        ))
                        await session.delete(state)
                        await session.commit()

    async def test_hint_is_persisted_and_reduces_score(self):
        start = self.query_data('era_game:play:guess_country')
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=self.send
        ), patch.object(Message, 'edit_reply_markup', new=AsyncMock()):
            async with self.sessions() as session:
                await game_callback(start, self.settings, session)
            room = await self._format_room()
            reference = room['id'] + '~' + room['token']
            hint = self.query_data(f'era_game:hint:{reference}')
            async with self.sessions() as session:
                await game_callback(hint, self.settings, session)
            from app.handlers.era_game_room import _format_item
            item = _format_item(room)
            correct = item.challenge.options.index(item.challenge.answer)
            answer = self.query_data(f'era_game:format_answer:{reference}:{correct}')
            async with self.sessions() as session:
                await game_callback(answer, self.settings, session)
        room = await self._format_room()
        assert room['hints_used'] == 2
        assert room['scores']['11'] == 3

    async def test_memory_restart_recovery_hides_sequence_and_resumes_recall(self):
        from app.handlers.era_game_room import _format_prompt

        start = self.query_data('era_game:play:memory')
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=self.send
        ), patch('app.handlers.era_game_room.asyncio.sleep', new=AsyncMock()):
            async with self.sessions() as session:
                await game_callback(start, self.settings, session)
        room = await self._format_room()
        assert room['memory_revealed'] is True
        text, markup = _format_prompt(room)
        assert 'Последовательность скрыта' in text
        assert '🔴 🔵 🟡' not in text
        assert markup is not None

    async def test_memory_initial_phase_has_no_answer_buttons(self):
        from app.handlers.era_game_room import _format_prompt

        start = self.query_data('era_game:play:memory')
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=self.send
        ), patch('app.handlers.era_game_room.asyncio.sleep', new=AsyncMock()):
            async with self.sessions() as session:
                await game_callback(start, self.settings, session)
        room = await self._format_room()
        room['memory_revealed'] = False
        text, markup = _format_prompt(room)
        assert 'Запомни порядок' in text and ' → ' in text
        assert markup is None

    async def test_content_reservation_is_per_user_and_exhaustion_is_explicit(self):
        from app.handlers.era_game_room import _reserve_format_item
        from app.services.game_content import items_for_mode
        from app.services.game_formats import GameMode

        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            first = await _reserve_format_item(session, mode=GameMode.TRUE_OR_MYTH, user_id=11, now=now)
            second = await _reserve_format_item(session, mode=GameMode.TRUE_OR_MYTH, user_id=11, now=now)
            another_player = await _reserve_format_item(session, mode=GameMode.TRUE_OR_MYTH, user_id=12, now=now)
            after_window = await _reserve_format_item(
                session, mode=GameMode.TRUE_OR_MYTH, user_id=11, now=now + timedelta(days=181)
            )
            await session.commit()
        usage_key = f"era_game:content_usage:{GameMode.TRUE_OR_MYTH.value}:11"
        async with self.sessions() as session:
            usage = {item.id: now.isoformat() for item in items_for_mode(GameMode.TRUE_OR_MYTH)}
            row = await session.scalar(select(AppSetting).where(AppSetting.key == usage_key))
            row.value = json.dumps(usage)
            await session.commit()
        async with self.sessions() as session:
            exhausted = await _reserve_format_item(
                session, mode=GameMode.TRUE_OR_MYTH, user_id=11, now=now
            )
            await session.commit()
        assert first and second and first.id != second.id
        assert exhausted is None
        assert another_player is not None
        assert after_window is not None

    async def test_team_duel_starts_and_keeps_team_scores_separate(self):
        from app.handlers.era_game_room import QUESTIONS

        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(
            Message, 'answer', new=self.send
        ):
            async with self.sessions() as session:
                await game_callback(self.query_data('era_game:duel'), self.settings, session)
            room = await self._read_room('duel')
            reference = 'duel~' + room['token']
            async with self.sessions() as session:
                await game_callback(self.query_data(f'era_game:duel_join:{reference}:A'), self.settings, session)
            async with self.sessions() as session:
                await game_callback(self.query_data(f'era_game:duel_join:{reference}:B', uid=12), self.settings, session)
            for uid in (11, 12):
                async with self.sessions() as session:
                    await game_callback(self.query_data(f'era_game:ready:{reference}', uid=uid), self.settings, session)
            room = await self._read_room('duel')
            assert room['status'] == 'playing'
            for _ in range(5):
                question = room['question']
                correct = QUESTIONS[question][2]
                reference = 'duel~' + room['token']
                for uid, choice in ((11, correct), (12, (correct + 1) % len(QUESTIONS[question][1]))):
                    answer = self.query_data(f'era_game:answer:{reference}:{choice}', uid=uid)
                    async with self.sessions() as session:
                        await game_callback(answer, self.settings, session)
                    room = await self._read_room('duel')
                    if room['status'] == 'finished':
                        break
                if room['status'] == 'finished':
                    break
            assert room['status'] == 'finished'
            assert room['team_scores'] == {'A': 5, 'B': 0}

    async def _read_room(self, room_id):
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == _key(-1001, 10, room_id)
            ))
            return _data(row)


class IdentifiedRoomTests(GameFixture, IsolatedAsyncioTestCase):
    async def click(self, data, uid=11, *, private=False, name=None):
        query = self.query({'id': 'unused', 'token': 'unused'}, uid=uid)
        query.data = data
        if name:
            query.from_user = TelegramUser(id=uid, first_name=name, is_bot=False)
        if private:
            query.message = Message(message_id=1, date=datetime.now(timezone.utc),
                                    chat=Chat(id=uid, type='private'), from_user=query.from_user).as_(self.bot)
        with patch('app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)), patch.object(Message, 'answer', new=self.send):
            async with self.sessions() as session:
                await game_callback(query, self.settings, session)
        return query

    async def room(self, kind='duel', *, private=False):
        key = _key(11 if private else -1001, None if private else 10, kind)
        async with self.sessions() as session:
            return _data(await session.scalar(select(AppSetting).where(AppSetting.key == key)))

    async def test_start_game_deep_link_reaches_the_live_private_handler(self):
        from aiogram.filters import CommandObject
        from app.handlers.emergency import rescue_start
        actor = TelegramUser(id=11, first_name='Анна', is_bot=False)
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=11, type='private'), from_user=actor).as_(self.bot)
        self.settings.general_chat_id = -1001
        with patch('app.handlers.emergency._subscription_ok', new=AsyncMock(return_value=True)), patch(
            'app.handlers.era_game_room._allowed', new=AsyncMock(return_value=True)
        ), patch.object(Message, 'answer', new=self.send):
            async with self.sessions() as session:
                user = await session.get(User, self.user_id)
                await rescue_start(message, self.bot, user, self.settings, SimpleNamespace(clear=AsyncMock()), session,
                                   command=CommandObject(prefix='/', command='start', args='game_logic'))
        async with self.sessions() as session:
            rooms = [_data(r) for r in (await session.scalars(select(AppSetting).where(AppSetting.key.like('era_game:11:None:f%')))).all()]
        assert len(rooms) == 1 and rooms[0]['mode'] == 'logic'
        assert rooms[0]['players'] == {'11': 'Анна'}
        assert self.send.await_count == 1

    async def test_unregistered_and_pending_clicks_do_not_create_or_join_rooms(self):
        await self.click('era_game:duel', 99)
        assert await self.room() == {}
        await self.click('era_game:duel')
        initial = await self.room()
        async with self.sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_id == 22))
            user.application_status = ApplicationStatus.PENDING
            await session.commit()
        query = await self.click(f"era_game:join:duel~{initial['token']}", 22)
        assert (await self.room())['participants'] == [11]
        assert query.answer.await_args.kwargs['url'].endswith('?start=games')
        assert self.send.await_count == 1

    async def test_menu_auto_joins_balanced_teams_and_one_card_shows_actual_names(self):
        for uid, name in ((11, 'Анна'), (22, 'Борис'), (33, 'Вера'), (12, 'Глеб')):
            await self.click('era_game:duel', uid, name=name)
        state = await self.room()
        assert state['teams'] == {'11': 'A', '22': 'B', '33': 'A', '12': 'B'}
        assert self.send.await_count == 1
        assert self.bot.edit_message_text.await_count == 3
        card = self.bot.edit_message_text.await_args.kwargs
        assert card['message_id'] == 66
        for uid, name in state['players'].items():
            assert name in card['text'] and f'<code>{uid}</code>' in card['text']
        assert '🔴 Команда А' in card['text'] and '🔵 Команда Б' in card['text']
        assert all('duel_join' not in (b.callback_data or '') for row in card['reply_markup'].inline_keyboard for b in row)

    async def test_duplicate_legacy_side_choice_never_moves_player_or_spams(self):
        await self.click('era_game:duel')
        state = await self.room()
        ref = f"duel~{state['token']}"
        await self.click(f'era_game:duel_join:{ref}:A', 22)
        before = await self.room()
        await self.click(f'era_game:duel_join:{ref}:B', 22)
        assert await self.room() == before
        assert before['teams']['22'] == 'B'
        assert self.send.await_count == 1

    async def test_leaving_rebalances_and_card_shows_remaining_people(self):
        for uid in (11, 22, 33):
            await self.click('era_game:duel', uid)
        state = await self.room()
        await self.click(f"era_game:leave:duel~{state['token']}", 22)
        state = await self.room()
        assert state['teams'] == {'11': 'A', '33': 'B'}
        assert state['ready'] == []
        assert '<code>22</code>' not in self.bot.edit_message_text.await_args.kwargs['text']

    async def test_ready_answer_and_result_all_edit_same_card_with_named_winners(self):
        from app.handlers.era_game_room import QUESTIONS
        await self.click('era_game:duel', name='Анна')
        await self.click('era_game:duel', 22, name='Борис')
        state = await self.room()
        for uid in (11, 22):
            await self.click(f"era_game:ready:duel~{state['token']}", uid)
        for _ in range(5):
            state = await self.room()
            correct = QUESTIONS[state['question']][2]
            await self.click(f"era_game:answer:duel~{state['token']}:{correct}", 11)
            partial = self.bot.edit_message_text.await_args.kwargs['text']
            assert '✅ ответ принят' in partial and '⏳ отвечает' in partial
            await self.click(f"era_game:answer:duel~{state['token']}:{(correct+1)%3}", 22)
        result = self.bot.edit_message_text.await_args.kwargs
        assert 'Победила 🔴 Команда А' in result['text']
        assert '<code>11</code>' in result['text'] and '<code>22</code>' in result['text']
        assert result['reply_markup'] is None and result['message_id'] == 66
        assert self.send.await_count == 1
        assert (await self.room())['rewards'] == {'11': 3}

    async def test_solo_public_button_redirects_and_private_game_stays_private(self):
        call = await self.click('era_game:solo')
        assert call.answer.await_args.kwargs['url'].endswith('?start=game_solo')
        assert self.send.await_count == 0
        await self.click('era_game:solo', private=True)
        private = await self.room('solo-11', private=True)
        assert private['participants'] == [11] and private['message_id'] == 66
        assert await self.room('solo-11') == {}

    async def test_private_solo_cannot_be_answered_by_a_different_registered_player(self):
        await self.click('era_game:solo', private=True)
        state = await self.room('solo-11', private=True)
        query = await self.click(f"era_game:answer:solo-11~{state['token']}:0", 22, private=True)
        assert (await self.room('solo-11', private=True))['answers'] == {}
        query.answer.assert_awaited()

    async def test_resume_after_new_session_edits_existing_card_without_consuming_question(self):
        await self.click('era_game:solo', private=True)
        state = await self.room('solo-11', private=True)
        await self.click('era_game:resume', private=True)
        assert await self.room('solo-11', private=True) == state
        assert self.send.await_count == 1
        assert self.bot.edit_message_text.await_args.kwargs['message_id'] == 66

    async def test_expiry_clears_buttons_and_does_not_post_another_message_after_restart(self):
        await self.click('era_game:duel')
        now = datetime.now(timezone.utc) + timedelta(minutes=5)
        assert await expire_game_rooms(self.sessions, self.bot, now=now) == 1
        assert await expire_game_rooms(self.sessions, self.bot, now=now) == 0
        card = self.bot.edit_message_text.await_args.kwargs
        assert card['reply_markup'] is None and 'Время игры истекло' in card['text']
        assert self.send.await_count == 1

    async def test_unknown_initial_send_outcome_never_posts_a_second_card(self):
        from aiogram.exceptions import TelegramNetworkError
        from aiogram.methods import SendMessage
        self.send.side_effect = TelegramNetworkError(method=SendMessage(chat_id=-1001, text='x'), message='timeout')
        await self.click('era_game:duel')
        assert (await self.room())['card_delivery'] == 'uncertain'
        await self.click('era_game:duel')
        assert self.send.await_count == 1

    async def test_private_cabinet_shows_only_own_team_and_latest_solo_results(self):
        from app.handlers.era_game_room import show_game_cabinet
        await self.click('era_game:duel', name='Анна')
        await self.click('era_game:duel', 22, name='Борис')
        await self.click('era_game:solo', private=True)
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=11, type='private')).as_(self.bot)
        with patch('app.handlers.era_game_room.ensure_topic', new=AsyncMock(return_value=10)), patch.object(Message, 'answer', new=self.send):
            self.settings.general_chat_id = -1001
            async with self.sessions() as session:
                user = await session.get(User, self.user_id)
                await show_game_cabinet(message, self.settings, session, user)
        text = self.send.await_args.args[0]
        assert 'Игры ЭРА' in text and 'Команда А' not in text
        assert '<code>' not in text and '#' not in text and len(text) < 400
        buttons = [button for row in self.send.await_args.kwargs['reply_markup'].inline_keyboard for button in row]
        assert any(button.callback_data == 'era_game:catalog:history' for button in buttons)
        async with self.sessions() as session:
            user = await session.get(User, self.user_id)
            with patch('app.handlers.era_game_room.ensure_topic', new=AsyncMock(return_value=10)), patch.object(Message, 'answer', new=self.send):
                await show_game_cabinet(message, self.settings, session, user, view='history')
        text = self.send.await_args.args[0]
        assert 'Команда А' in text and 'Команда Б' in text
        assert 'Анна' in text and 'Борис' in text
        assert '<code>11</code>' in text and '<code>22</code>' in text
        assert '#' not in text


    async def test_resume_matches_the_latest_private_game_shown_in_cabinet(self):
        await self.click('era_game:play:true_or_myth', private=True)
        await self.click('era_game:play:guess_country', private=True)
        await self.click('era_game:resume', private=True)
        assert 'Угадай страну' in self.bot.edit_message_text.await_args.kwargs['text']

    async def test_legacy_public_resume_cannot_reopen_a_solo_room_in_the_group(self):
        async with self.sessions() as session:
            session.add(AppSetting(key=_key(-1001, 10, 'solo-11'), value={
                'id': 'solo-11', 'kind': 'solo', 'participants': [11], 'status': 'playing',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': (datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
                'token': 'legacy', 'message_id': 66, 'question': 0}))
            await session.commit()
        query = await self.click('era_game:resume')
        assert 'Открытой игры нет' in query.answer.await_args.args[0]
        self.bot.edit_message_text.assert_not_awaited()


    async def test_public_rules_popup_fits_telegram_limit(self):
        query = await self.click('era_game:rules')
        assert len(query.answer.await_args.args[0]) <= 200
        assert query.answer.await_args.kwargs['show_alert'] is True


def test_game_name_escaping_does_not_leak_questionnaire_fields():
    from app.services.game_room_presenter import remember_player, roster
    room = {'participants': [11], 'status': 'waiting'}
    person = TelegramUser(id=11, first_name='<b>Имя & тест</b>', is_bot=False)
    remember_player(room, person)
    text = roster(room)
    assert '&lt;b&gt;Имя &amp; тест&lt;/b&gt;' in text
    assert '<b>Имя & тест</b>' not in text
    assert set(room['players']) == {'11'}


class LegacyGameIdentityTests(GameFixture, IsolatedAsyncioTestCase):
    async def test_legacy_roster_uses_public_username_and_telegram_name_never_form_name(self):
        from app.handlers.era_game_room import _hydrate_player_names
        from app.services.game_room_presenter import roster
        async with self.sessions() as session:
            person = await session.get(User, self.user_id)
            person.username = 'public_name'
            person.first_name = 'PRIVATE_QUESTIONNAIRE_NAME'
            await session.commit()
            room = {'kind': 'duel', 'participants': [11, 22], 'teams': {'11': 'A', '22': 'B'}, 'players': {'11': 'Участник'}}
            self.bot.get_chat = AsyncMock(return_value=SimpleNamespace(first_name='Телеграм & имя', last_name=None))
            await _hydrate_player_names(session, room, self.bot)
        text = roster(room, result=True)
        assert '@public_name' in text and 'Телеграм &amp; имя' in text
        assert 'PRIVATE_QUESTIONNAIRE_NAME' not in text and 'Участник' not in text
        self.bot.get_chat.assert_awaited_once_with(22)

    async def test_catalog_edit_reuses_existing_card_and_never_creates_topic(self):
        from app.handlers.era_game_room import show_game_cabinet
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=11, type='private')).as_(self.bot)
        edit = AsyncMock()
        topic = AsyncMock(return_value=None)
        modes = set()
        async with self.sessions() as session:
            person = await session.get(User, self.user_id)
            self.settings.general_chat_id = -1001
            with patch.object(Message, 'edit_text', new=edit), patch.object(Message, 'answer', new=self.send), patch('app.handlers.era_game_room.ensure_topic', new=topic):
                for view in ('quiz', 'puzzle', 'rules'):
                    await show_game_cabinet(message, self.settings, session, person, view=view, edit=True)
                    buttons = [button for row in edit.await_args.kwargs['reply_markup'].inline_keyboard for button in row]
                    modes.update(button.callback_data for button in buttons if button.callback_data.startswith('era_game:play:') or button.callback_data == 'era_game:solo')
        assert len(modes) == 9
        assert self.send.await_count == 0 and edit.await_count == 3
        assert all(call.kwargs.get('create_if_missing') is False for call in topic.await_args_list)


def test_long_escaped_team_names_fit_telegram_card_without_repeating_the_reward_roster():
    from app.handlers.era_game_room import _room_view
    room = {'kind': 'team', 'status': 'finished', 'participants': list(range(1000000000, 1000000008)),
            'players': {str(uid): '&' * 60 for uid in range(1000000000, 1000000008)},
            'scores': {str(uid): 5 for uid in range(1000000000, 1000000008)},
            'rewards': {str(uid): 3 for uid in range(1000000000, 1000000008)}}
    text, _ = _room_view(room)
    assert len(text) < 4096 and text.count('🏅 <a') == 8
    assert all(text.count(f'<code>{uid}</code>') == 1 for uid in room['participants'])
    assert text.count('ЭРА +3') == 8


class DurableGameHistoryTests(GameFixture, IsolatedAsyncioTestCase):
    async def test_results_survive_replacement_and_filter_other_players_in_both_json_encodings(self):
        from app.handlers.era_game_room import _recent_game_results, _store_game_result
        async with self.sessions() as session:
            for token, uid, mode in [('first', 11, 'solo'), ('second', 11, 'solo'), ('stranger', 22, 'solo')]:
                room = {'status': 'finished', 'session_token': token, 'finished_at': datetime.now(timezone.utc).isoformat(),
                        'participants': [uid], 'kind': mode, 'scores': {str(uid): 2}}
                await _store_game_result(session, room)
            session.add(AppSetting(key=_key(11, None, 'solo-11'), value={'status': 'playing', 'participants': [11]}))
            session.add(AppSetting(key='game-result:team-object', value={'mode': 'duel', 'participants': [11, 22],
                'finished_at': datetime.now(timezone.utc).isoformat(), 'scores': {'11': 3}}))
            await session.commit()
            mine = await _recent_game_results(session, 11)
            team = await _recent_game_results(session, 11, team=True)
        assert len(mine) == 2 and {row['session_token'] for row in mine} == {'first', 'second'}
        assert len(team) == 1 and team[0]['kind'] == 'duel'
        assert all(11 in row['participants'] for row in mine + team)

    async def test_legacy_finished_room_is_preserved_once_without_awarding_points(self):
        from app.handlers.era_game_room import show_game_cabinet, _recent_game_results
        async with self.sessions() as session:
            session.add(AppSetting(key=_key(11, None, 'solo-11'), value={'status': 'finished',
                'session_token': 'legacy-finished', 'participants': [11], 'kind': 'solo',
                'finished_at': datetime.now(timezone.utc).isoformat(), 'scores': {'11': 4}}))
            await session.commit()
            message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=11, type='private')).as_(self.bot)
            user = await session.get(User, self.user_id)
            with patch.object(Message, 'answer', new=self.send):
                for _ in range(2):
                    await show_game_cabinet(message, self.settings, session, user, view='history')
                    await session.commit()
            results = await _recent_game_results(session, 11)
            assert len(results) == 1 and results[0]['scores']['11'] == 4
            assert not (await session.scalars(select(PointTransaction))).all()
            assert '4 очк.' in self.send.await_args.args[0]

    async def test_expired_stored_playing_room_does_not_offer_continue(self):
        from app.handlers.era_game_room import show_game_cabinet
        async with self.sessions() as session:
            session.add(AppSetting(key=_key(11, None, 'solo-11'), value={'status': 'playing',
                'participants': [11], 'kind': 'solo', 'expires_at': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}))
            await session.commit()
            message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=11, type='private')).as_(self.bot)
            user = await session.get(User, self.user_id)
            with patch.object(Message, 'answer', new=self.send):
                await show_game_cabinet(message, self.settings, session, user)
        assert 'Можно продолжить' not in self.send.await_args.args[0]
        assert not any(b.callback_data == 'era_game:resume' for row in self.send.await_args.kwargs['reply_markup'].inline_keyboard for b in row)


def test_format_completion_mentions_the_awarded_balance_once():
    from app.handlers.era_game_room import _room_view
    room = {'mode': 'true_or_myth', 'status': 'finished', 'participants': [11], 'scores': {'11': 1},
            'rewards': {'11': 1}, 'result_text': '✅ Верно!\n\nОчки за раунд: 1. Баллы ЭРА: +1.'}
    text, _ = _room_view(room)
    assert text.count('Баллы ЭРА:') == 1


def test_durable_format_title_uses_mode_when_optional_kind_is_null():
    from app.services.game_room_presenter import room_heading
    assert room_heading({'kind': None, 'mode': 'guess_country'}) == '<b>🌍 Угадай страну</b>'
