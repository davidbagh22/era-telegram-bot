"""Additional fixtures, explicitly forbidden outside the local E2E database."""
import asyncio
from datetime import date, time, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.database.models import Event, EventRegistration, User
from app.database.session import create_engine_and_sessionmaker
from app.services import certificate_service, ranking_season_service
from app.services.participation_lifecycle_service import complete_onboarding
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus


async def seed():
    settings=get_settings();url=make_url(settings.database_url)
    if not settings.dev_auth_enabled or url.drivername!='sqlite+aiosqlite' or Path(url.database or '').name!='e2e.db':
        raise RuntimeError('Only the throwaway SQLite e2e.db with DEV_AUTH_ENABLED is allowed')
    engine,sessions=create_engine_and_sessionmaker(settings.database_url)
    try:
        async with sessions() as session:
            admin=await session.scalar(select(User).where(User.telegram_id==900003))
            user=User(telegram_id=900011,first_name='E2E Certificate Holder',application_status=ApplicationStatus.APPROVED)
            session.add(user);await session.flush()
            await complete_onboarding(session,user)
            event=Event(title='E2E Подтверждённое участие',description='Only local E2E',event_date=date.today()-timedelta(days=1),
                        event_time=time(12),location='Ереван',format='offline',created_by=admin.id,status=EventStatus.COMPLETED)
            session.add(event);await session.flush()
            session.add(EventRegistration(user_id=user.id,event_id=event.id,status=RegistrationStatus.ATTENDED));await session.flush()
            snapshot=await certificate_service.certificate_snapshot(session,user.id,event.id,'E2E Тестовый подписант')
            await certificate_service.issue_certificate(session,admin,settings,user_id=user.id,event_id=event.id,
                signatory=snapshot['signatory'],request_key='e2e-certificate',expected_hash=certificate_service.snapshot_hash(snapshot))
            await ranking_season_service.create_season(session,admin,settings,title='E2E Сезон',
                starts_on=date.today().isoformat(),ends_on=(date.today()+timedelta(days=30)).isoformat())
            await session.commit()
        print('Readiness E2E fixtures: own certificate and a ranking season, no Telegram calls')
    finally:await engine.dispose()


if __name__=='__main__':asyncio.run(seed())
