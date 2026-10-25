import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.config import Settings
from app.database.base import Base
from app.database.models import PointTransaction, User
from app.services import ranking_season_service as service
from app.utils.constants import ApplicationStatus, PointCategory, Role


def test_season_boundaries_corrections_frozen_archive_and_no_balance_reset():
    async def scenario():
        engine=create_async_engine('sqlite+aiosqlite:///:memory:')
        try:
            async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine,expire_on_commit=False)() as session:
                settings=Settings(bot_token='0000000000:TEST')
                actor=User(telegram_id=9901,first_name='Admin',role=Role.ADMIN,application_status=ApplicationStatus.APPROVED)
                user=User(telegram_id=9902,first_name='Member',application_status=ApplicationStatus.APPROVED)
                session.add_all([actor,user]);await session.flush()
                now=datetime(2026,10,19,12,tzinfo=timezone.utc)
                with patch.object(service,'now_utc',return_value=now):
                    row=await service.create_season(session,actor,settings,title='Осень ЭРА',starts_on='2026-10-19',ends_on='2026-10-20')
                    with pytest.raises(ValueError,match='пересекается'):
                        await service.create_season(session,actor,settings,title='Ещё сезон',starts_on='2026-10-20',ends_on='2026-10-21')
                    with pytest.raises(PermissionError):
                        await service.create_season(session,user,settings,title='Чужой сезон',starts_on='2026-11-01',ends_on='2026-11-02')
                    start=datetime.fromisoformat(row.value['starts_at']);end=datetime.fromisoformat(row.value['ends_at'])
                    assert start==datetime(2026,10,18,20,tzinfo=timezone.utc)
                    txs=[(-1,90,PointCategory.TASK),(0,100,PointCategory.TASK),(1,-10,PointCategory.MANUAL),
                         (2,500,PointCategory.DIGITAL_ENGAGEMENT),(3,-30,PointCategory.REDEMPTION)]
                    for offset,points,category in txs:
                        session.add(PointTransaction(user_id=user.id,points=points,category=category,reason='Test',
                                                     created_at=start+timedelta(seconds=offset)))
                    session.add(PointTransaction(user_id=user.id,points=50,category=PointCategory.TASK,reason='Boundary',created_at=end))
                    await session.flush()
                    board=await service.season_leaderboard(session,user,row.value['id'])
                    assert board.me.points==90
                    assert row.value['results'] is None
                with patch.object(service,'now_utc',return_value=end+timedelta(minutes=1)):
                    await service.finalize_season(session,row)
                    snapshot=row.value.copy()
                    session.add(PointTransaction(user_id=user.id,points=700,category=PointCategory.TASK,reason='Late',created_at=end+timedelta(seconds=1)))
                    await session.flush()
                    await service.finalize_season(session,row)
                    assert row.value==snapshot
                    board=await service.season_leaderboard(session,user,row.value['id'])
                    assert board.me.points==90
                    user.is_archived=True;await session.flush()
                    assert (await service.season_leaderboard(session,actor,row.value['id'])).entries==[]
                from sqlalchemy import select,func
                assert await session.scalar(select(func.sum(PointTransaction.points)))==1400
        finally:await engine.dispose()
    asyncio.run(scenario())
