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
from app.handlers.era_game_room import _data, _key, _new_room, game_callback, quiz_markup
from app.services.game_rewards_service import award_game_points
from app.services.game_room_expiry_service import expire_game_rooms
from app.utils.constants import ApplicationStatus


class GameStateTests(IsolatedAsyncioTestCase):
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

    async def test_abandoned_lobby_does_not_consume_content(self):
        await self.new_room('team')
        async with self.sessions() as session:
            usage = await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage'))
            assert usage is None

    async def test_question_exhaustion_never_silently_repeats(self):
        from app.handlers.era_game_room import QUESTIONS
        async with self.sessions() as session:
            session.add(AppSetting(key='era_game:question_usage', value=json.dumps({str(i):datetime.now(timezone.utc).isoformat() for i in range(len(QUESTIONS))})))
            await session.commit()
        assert (await self.new_room())['status'] == 'exhausted'


def test_round_callbacks_fit_telegram_limit():
    for row in quiz_markup('solo-999999999999~abcdef123456', ('One','Two')).inline_keyboard:
        assert len(row[0].callback_data.encode()) <= 64
