"""Real PostgreSQL proof for concurrent editorial/support/campaign workers."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.autocontent_models import GeneralCustomContent
from app.database.models import AppSetting, Broadcast, User, UserQuestion
from app.database.system_models import NotificationDelivery
from app.services.admin_broadcast_service import control_broadcast, resume_broadcasts, send_personal_broadcast
from app.services.book_club_service import (approve_editorial_item, editorial_revision, run_editorial_queue,
    save_editorial_item, save_editorial_settings)
from app.services.scheduler_service import deliver_support_answers
from app.utils.constants import ApplicationStatus, Role

MATERIAL = ('Название: Проверка очереди\nАвтор: CI\nВведение: Изолированный тест.\n'
            'Главная мысль: Публикация выполняется один раз.\nВопрос: Доставлен ли выпуск?')


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('Only isolated era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 9_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    settings = Settings(bot_token='0000000000:CIQUEUETOKEN', database_url=url, general_chat_id=-uid)
    now = datetime(2026, 10, 17, 16, tzinfo=timezone.utc)
    calls = []
    async def send(chat_id, body, **kwargs):
        assert chat_id in {uid, -uid}
        if chat_id < 0:
            assert kwargs['message_thread_id'] == 26216
        calls.append((chat_id, body))
        await asyncio.sleep(0.01)
        return SimpleNamespace(message_id=len(calls))
    bot = SimpleNamespace(send_message=send)
    try:
        async with sessions() as session:
            editor = User(telegram_id=uid, first_name='CI Editor', role=Role.ADMIN,
                          application_status=ApplicationStatus.APPROVED, book_club_subscribed=True)
            session.add(editor)
            await session.flush()
            editor_id = editor.id
            session.add(AppSetting(key=f'general_forum:{-uid}:literature', value=json.dumps({'thread_id': 26216})))
            item = await save_editorial_item(session, MATERIAL, actor_id=editor.id)
            item_id, content_id = item.id, item.content_id
            await approve_editorial_item(session, item.id, editorial_revision(item), actor_id=editor.id)
            next_item = await save_editorial_item(session, MATERIAL.replace('Проверка очереди', 'Следующий выпуск'), actor_id=editor.id)
            next_id = next_item.id
            await approve_editorial_item(session, next_item.id, editorial_revision(next_item), actor_id=editor.id)
            await save_editorial_settings(session, actor_id=editor.id, enabled=True)
            await session.commit()
        await asyncio.wait_for(asyncio.gather(*(
            run_editorial_queue(bot, settings, sessions, now=now) for _ in range(8))), 60)
        assert len(calls) == 2, len(calls)
        async with sessions() as session:
            assert (await session.get(GeneralCustomContent, item_id)).is_skipped
            assert not (await session.get(GeneralCustomContent, next_id)).is_skipped
            assert await session.scalar(select(func.count()).select_from(AppSetting).where(
                AppSetting.key == 'book-club-editorial-day:2026-10-17')) == 1
            receipt = await session.scalar(select(NotificationDelivery).where(
                NotificationDelivery.delivery_key == f'general-topic:literature:editorial:{content_id}'))
            assert receipt.status == 'sent' and receipt.attempt_count == 1
            question = UserQuestion(user_id=editor_id, text='CI question', status='answer_pending',
                                    admin_answer='CI saved answer', answered_by=editor_id)
            session.add(question)
            await session.commit()
            question_id = question.id
        await asyncio.wait_for(asyncio.gather(*(
            deliver_support_answers(bot, settings, sessions) for _ in range(8))), 60)
        assert len(calls) == 3, len(calls)
        async with sessions() as session:
            assert (await session.get(UserQuestion, question_id)).status == 'answered'
        # Stop the worker while the final Telegram request is still in flight.
        async def cancel_during_send(chat_id, body, **kwargs):
            async with sessions() as session:
                item = await session.scalar(select(Broadcast).where(Broadcast.author_id == editor_id))
                await control_broadcast(session, settings, actor=await session.get(User, editor_id), campaign_id=item.id, action='cancel')
                await session.commit()
            return SimpleNamespace(message_id=99)
        async with sessions() as session:
            await send_personal_broadcast(SimpleNamespace(send_message=cancel_during_send), session,
                audience='city', filter_value=f'CI-{uid}', text='CI campaign', author_id=editor_id,
                settings=settings, campaign_key='cancel-race-empty')
            # First prove the empty audience finishes without any Telegram call.
            campaign = await session.scalar(select(Broadcast).where(Broadcast.author_id == editor_id))
            assert campaign.status == 'sent'
            campaign.status = 'sending'
            campaign.audience_filter_json = {**campaign.audience_filter_json, 'recipient_ids': [editor_id]}
            await session.commit()
        await asyncio.wait_for(resume_broadcasts(SimpleNamespace(send_message=cancel_during_send), settings, sessions), 60)
        async with sessions() as session:
            assert (await session.scalar(select(Broadcast).where(Broadcast.author_id == editor_id))).status == 'cancelled'
    finally:
        await engine.dispose()
    print('PostgreSQL: 8 workers produce one editorial issue and one support answer; in-flight cancellation wins')


if __name__ == '__main__':
    asyncio.run(main())
