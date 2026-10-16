"""Prove one management summary under concurrent schedulers on an isolated DB."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import AppSetting, User
from app.database.system_models import NotificationDelivery
from app.services.admin_analytics_service import send_management_reports
from app.utils.constants import ApplicationStatus, Role


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('Only the isolated era_test database is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 8_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    now = datetime(2026, 10, 16, 6, tzinfo=timezone.utc)
    settings = Settings(bot_token='0000000000:CIREPORTTOKEN', database_url=url,
                        feature_management_reports='TESTERS', management_report_recipient_ids=[uid])
    calls = []
    async def send(chat_id, body, **kwargs):
        assert chat_id == uid
        calls.append(body)
        await asyncio.sleep(0.01)
        return SimpleNamespace(message_id=len(calls))
    try:
        async with sessions() as session:
            session.add(User(telegram_id=uid, first_name='CI Report', role=Role.ADMIN,
                             application_status=ApplicationStatus.APPROVED, created_at=now-timedelta(days=2)))
            await session.commit()
        await asyncio.wait_for(asyncio.gather(*(
            send_management_reports(SimpleNamespace(send_message=send), settings, sessions, now=now)
            for _ in range(8)
        )), 60)
        assert len(calls) == 3, len(calls)
        async with sessions() as session:
            receipt = await session.scalar(select(NotificationDelivery).where(NotificationDelivery.delivery_key == f'daily:2026-10-16:{uid}'))
            assert receipt.status == 'sent' and receipt.attempt_count == 1
            keys = [f'{period}:{stamp}:{uid}' for period, stamp in [('daily','2026-10-16'),('weekly','2026-10-12'),('monthly','2026-10-01')]]
            receipts = (await session.scalars(select(NotificationDelivery).where(NotificationDelivery.delivery_key.in_(keys)))).all()
            assert len(receipts) == 3 and all(row.status == 'sent' and row.attempt_count == 1 for row in receipts)
            assert await session.scalar(select(func.count()).select_from(AppSetting).where(AppSetting.key == 'management-report:daily:2026-10-16')) == 1
    finally:
        await engine.dispose()
    print('PostgreSQL management summary: 8 concurrent schedulers, one snapshot and delivery per period')


if __name__ == '__main__':
    asyncio.run(main())
