import json
import random
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.handlers.era_game_room import QUESTIONS, _reserve_questions, _room_view, _format_prompt
from app.services.game_content import choose_quiz_pack, items_for_mode
from app.services.game_formats import GameMode


def test_quiz_pack_mixes_five_themes_and_has_no_duplicate_question():
    bank = items_for_mode(GameMode.SOLO_QUIZ)
    pack = choose_quiz_pack(list(range(len(bank))), 5, rng=random.Random(42))
    assert len(set(pack)) == 5
    assert len({bank[index].category for index in pack}) == 5
    assert pack != [0, 1, 2, 3, 4]


class GameVarietyTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_180_days_of_daily_quizzes_do_not_stop_or_repeat_within_30_days(self):
        now = datetime(2026, 10, 17, tzinfo=timezone.utc)
        last_seen = {}
        for day in range(180):
            async with self.sessions() as session:
                pack = await _reserve_questions(session, now+timedelta(days=day), 5,
                                                user_ids=(11,), mode=('solo_quiz', 'team_quiz', 'team_duel')[day % 3])
                await session.commit()
            assert len(pack) == len(set(pack)) == 5
            for index in pack:
                assert index not in last_seen or day-last_seen[index] >= 30
                last_seen[index] = day

    async def test_legacy_team_history_is_respected_by_solo_and_exhaustion_does_not_reset_it(self):
        now = datetime.now(timezone.utc)
        used = {str(index): now.isoformat() for index in range(len(QUESTIONS))}
        async with self.sessions() as session:
            session.add(AppSetting(key='era_game:question_usage:team_duel:11', value=json.dumps(used)))
            await session.commit()
            assert await _reserve_questions(session, now, 5, user_ids=(11,), mode='solo_quiz') == []
            stored = await session.scalar(select(AppSetting).where(AppSetting.key == 'era_game:question_usage:team_duel:11'))
            assert json.loads(stored.value) == used


def test_hints_are_readable_in_the_card_and_finished_solo_offers_a_new_round():
    item = items_for_mode(GameMode.GUESS_COUNTRY)[0]
    room = {'id': 'f3-11', 'mode': 'guess_country', 'item_id': item.id, 'status': 'playing',
            'token': 'test', 'session_token': 'test', 'participants': [11], 'players': {'11': 'A'},
            'hints_used': 1, 'first_hint_free': True, 'expires_at': datetime.now(timezone.utc).isoformat()}
    text, markup = _format_prompt(room)
    assert item.challenge.hints[0] in text
    assert any(button.text == '💡 Подсказка 2/3' for row in markup.inline_keyboard for button in row)
    room.update(status='finished', result_text='✅ Верно!', scores={'11': 4})
    _, markup = _room_view(room)
    assert any(button.callback_data == 'era_game:play:guess_country'
               for row in markup.inline_keyboard for button in row)
