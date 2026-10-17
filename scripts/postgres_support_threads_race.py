"""Run only on isolated CI PostgreSQL; prove conversation concurrency outcomes."""
import asyncio
import hashlib
import os
import uuid
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import SupportMessage, User, UserQuestion
from app.database.system_models import NotificationDelivery
from app.services.support_service import append_support_message, deliver_support_thread_messages
from app.utils.constants import ApplicationStatus, Role


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('Only isolated era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 10_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    settings = Settings(bot_token='0000000000:SUPPORTCI', database_url=url, feature_support_threads='ALL')
    try:
        async with sessions() as session:
            member = User(telegram_id=uid, first_name='CI member', application_status=ApplicationStatus.APPROVED)
            staff = User(telegram_id=uid+1, first_name='CI staff', application_status=ApplicationStatus.APPROVED, role=Role.ADMIN)
            other_staff = User(telegram_id=uid+2, first_name='CI other staff', application_status=ApplicationStatus.APPROVED, role=Role.ADMIN)
            session.add_all([member, staff, other_staff])
            await session.flush()
            member_id, staff_id, other_staff_id = member.id, staff.id, other_staff.id
            question = UserQuestion(user_id=member_id, text='Original CI question')
            session.add(question)
            await session.commit()
            question_id = question.id

        async def append(source, revision, actor_id=None):
            async with sessions() as session:
                try:
                    row, created = await append_support_message(session, settings, question_id=question_id,
                        actor_id=actor_id or staff_id, staff=True, text='The same response', source_key=source, expected_revision=revision)
                    await session.commit()
                    return row.id, created
                except ValueError as exc:
                    assert str(exc) == 'stale_thread'
                    await session.rollback()
                    return None, False

        duplicates = await asyncio.wait_for(asyncio.gather(*(append(f'CI-{uid}:same', 0) for _ in range(8))), 45)
        assert len({row_id for row_id, _ in duplicates}) == 1 and sum(created for _, created in duplicates) == 1
        async with sessions() as session:
            current = (await session.get(UserQuestion, question_id)).thread_revision
        competing = await asyncio.wait_for(asyncio.gather(*(append(f'CI-{uid}:{i}', current,
            staff_id if i % 2 else other_staff_id) for i in range(8))), 45)
        assert sum(created for _, created in competing) == 1 and sum(row_id is None for row_id, _ in competing) == 7

        calls = []
        async def send(chat_id, body, **kwargs):
            assert chat_id == uid
            calls.append(body)
            await asyncio.sleep(0.01)
            return SimpleNamespace(message_id=len(calls))

        await asyncio.wait_for(asyncio.gather(*(deliver_support_thread_messages(
            SimpleNamespace(send_message=send), settings, sessions) for _ in range(8))), 60)
        await deliver_support_thread_messages(SimpleNamespace(send_message=send), settings, sessions)
        assert len(calls) == 2 and calls[0] == calls[1]
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(SupportMessage).where(
                SupportMessage.question_id == question_id)) == 3
            message_ids = list((await session.scalars(select(SupportMessage.id).where(
                SupportMessage.question_id == question_id, SupportMessage.direction == 'staff'))).all())
            rows = (await session.scalars(select(NotificationDelivery).where(
                NotificationDelivery.delivery_key.in_([
                    f'support-thread:{message_id}:' + hashlib.sha256(str(uid).encode()).hexdigest()[:12]
                    for message_id in message_ids])))).all()
            assert len(rows) == 2 and all(r.status == 'sent' and r.attempt_count == 1 for r in rows)
        print('PostgreSQL: 8 duplicate webhooks create one reply; 8 stale competing replies accept one; '
              '8 delivery workers send each distinct message once, including identical text in another round')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
