"""Concurrency proofs only on the isolated local CI database."""
import asyncio
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.certificate_models import CertificateIssue
from app.database.models import AppSetting, AuditLog, Event, EventRegistration, PortfolioItem, User
from app.services import certificate_service as cert, ranking_season_service as season
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus, Role


async def main():
    url=os.environ['DATABASE_URL'];parsed=make_url(url)
    if parsed.database!='era_test' or parsed.host not in {'localhost','127.0.0.1','::1'}:
        raise RuntimeError('Only isolated local era_test is allowed')
    engine=create_async_engine(url);sessions=async_sessionmaker(engine,expire_on_commit=False)
    settings=Settings(bot_token='0000000000:CITEST')
    uid=50_000_000_000+int(uuid.uuid4().hex[:7],16)
    try:
        async with sessions() as session:
            actor=User(telegram_id=uid,first_name='CI issuer',role=Role.ADMIN,application_status=ApplicationStatus.APPROVED)
            user=User(telegram_id=uid+1,first_name='CI participant',application_status=ApplicationStatus.APPROVED)
            session.add_all([actor,user]);await session.flush()
            event=Event(title='CI certificate race',description='Isolated fixture',event_date=date.today(),event_time=time(12),
                        location='CI',format='offline',status=EventStatus.COMPLETED,created_by=actor.id)
            session.add(event);await session.flush()
            session.add(EventRegistration(user_id=user.id,event_id=event.id,status=RegistrationStatus.ATTENDED))
            await session.commit();aid,uid,eid=actor.id,user.id,event.id
            snapshot=await cert.certificate_snapshot(session,uid,eid,'CI authorized signatory')
            digest=cert.snapshot_hash(snapshot)
        keys=[uuid.uuid4().hex for _ in range(8)]
        async def issue(key):
            async with sessions() as session:
                row=await cert.issue_certificate(session,await session.get(User,aid),settings,user_id=uid,event_id=eid,
                    signatory=snapshot['signatory'],request_key=key,expected_hash=digest)
                await session.commit();return row.id
        ids=await asyncio.wait_for(asyncio.gather(*(issue(k) for k in keys)),45)
        assert len(set(ids))==1,ids
        async def revoke():
            async with sessions() as session:
                await cert.revoke_certificate(session,await session.get(User,aid),settings,ids[0],'CI correction')
                await session.commit()
        await asyncio.wait_for(asyncio.gather(*(revoke() for _ in range(8))),45)
        newids=await asyncio.wait_for(asyncio.gather(*(issue(uuid.uuid4().hex) for _ in range(8))),45)
        assert len(set(newids))==1 and newids[0]!=ids[0],newids
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(CertificateIssue).where(CertificateIssue.user_id==uid))==2
            assert await session.scalar(select(func.count()).select_from(PortfolioItem).where(PortfolioItem.user_id==uid))==2
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id==ids[0],AuditLog.action=='certificate.revoked'))==1
        # Existing CI probes create no ranking seasons. Distinct UTC dates are
        # used solely here; no production service or Telegram is contacted.
        today=datetime.now(timezone.utc).date()+timedelta(days=10)
        async def create():
            async with sessions() as session:
                try:
                    row=await season.create_season(session,await session.get(User,aid),settings,title='CI season',
                        starts_on=today.isoformat(),ends_on=(today+timedelta(days=1)).isoformat())
                    await session.commit();return row.id
                except ValueError:
                    await session.rollback();return None
        winners=await asyncio.wait_for(asyncio.gather(*(create() for _ in range(8))),45)
        assert len([i for i in winners if i])==1,winners
        sid=next(i for i in winners if i)
        async def close():
            async with sessions() as session:
                row=await session.get(AppSetting,sid)
                await season.finalize_season(session,row,now=datetime.fromisoformat(row.value['ends_at'])+timedelta(minutes=1))
                await session.commit()
        await asyncio.wait_for(asyncio.gather(*(close() for _ in range(8))),45)
        async with sessions() as session:
            row=await session.get(AppSetting,sid)
            assert row.value['results']==[]
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='ranking.season_closed'))==1
        from app.services import data_rights_service
        async with sessions() as session:
            holder=await session.get(User,uid)
            deletion=await data_rights_service.request_deletion(session,holder,None)
            await data_rights_service.fulfill_deletion_request(session,deletion,admin=await session.get(User,aid),approve=True)
            await session.commit()
            assert (await session.get(CertificateIssue,newids[0])).status=='revoked'
            assert await session.scalar(select(func.count()).select_from(CertificateIssue).where(CertificateIssue.user_id==uid))==2
        from app.services.analytics_snapshot_service import build_analytics_snapshot, build_event_analytics, build_project_analytics
        from app.services.analytics_growth_service import build_growth_snapshot
        from app.services.admin_analytics_service import build_scoped_leader_operations
        async with sessions() as session:
            for days in (7,30,90):
                snapshot=await build_analytics_snapshot(session,days=days)
                values={metric.key:metric.value for metric in snapshot.metrics}
                assert values['active'] <= values['members']
                assert values['retention'] is None or 0 <= values['retention'] <= 100
                events=await build_event_analytics(session,days=days)
                rate=next(metric.value for metric in events.metrics if metric.key=='attendance')
                assert rate is None or 0 <= rate <= 100
                await build_project_analytics(session,days=days)
            assert len((await build_growth_snapshot(session)).stages)==6
            await build_scoped_leader_operations(session,await session.get(User,aid),settings)
        print('PostgreSQL: analytics 7/30/90, observed growth, event/project aggregates and scoped operations execute on migrated schema')
        print('PostgreSQL: approved anonymization preserves certificate numbers without foreign-key violations')
        print('PostgreSQL: 8 concurrent issues -> 1 certificate; 8 revocations -> 1 audit; 8 corrections -> 1 new revision; 8 season creations/closures -> 1 definition and 1 archive')
    finally:
        await engine.dispose()


if __name__=='__main__':asyncio.run(main())
