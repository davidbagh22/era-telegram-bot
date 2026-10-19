import asyncio
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.api.deps import get_current_user, get_session
from app.api.v1.career import router
from app.config import Settings
from app.database.base import Base
from app.database.certificate_models import CertificateIssue
from app.database.models import Event, EventRegistration, PermissionGrant, PortfolioItem, User
from app.services import career_service, certificate_service as service
from app.services.certificate_pdf_service import build_certificate_pdf
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus, Role


def test_issuance_revocation_reissue_and_current_permissions():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                settings = Settings(bot_token="0000000000:TEST")
                actor = User(telegram_id=4401, first_name="Редактор", application_status=ApplicationStatus.APPROVED)
                target = User(telegram_id=4402, first_name="Անի", last_name="Участница", application_status=ApplicationStatus.APPROVED)
                session.add_all([actor,target]); await session.flush()
                grant = PermissionGrant(user_id=actor.id, permission="portfolio.review", scope_type="global", scope_id=0,
                                        is_active=True, granted_by=actor.id)
                event = Event(title="Волонтёрство ЭРА", description="Событие", event_date=date(2026,10,19),
                              event_time=time(12), location="Ереван", format="offline", created_by=actor.id,
                              status=EventStatus.COMPLETED)
                session.add_all([grant,event]); await session.flush()
                reg = EventRegistration(event_id=event.id, user_id=target.id, status=RegistrationStatus.REGISTERED)
                session.add(reg); await session.flush()
                with pytest.raises(ValueError, match="подтверждённым"):
                    await service.certificate_snapshot(session,target.id,event.id,"Тестовый подписант")
                reg.status=RegistrationStatus.ATTENDED; await session.flush()
                snapshot = await service.certificate_snapshot(session,target.id,event.id,"Тестовый подписант")
                args=dict(user_id=target.id,event_id=event.id,signatory=snapshot['signatory'],request_key="first",
                          expected_hash=service.snapshot_hash(snapshot))
                with pytest.raises(ValueError, match="изменились"):
                    await service.issue_certificate(session,actor,settings,**(args | {"expected_hash":"bad"}))
                issue=await service.issue_certificate(session,actor,settings,**args)
                assert issue.document_number == "ERA-CERT-000001"
                assert (await service.issue_certificate(session,actor,settings,**args)).id == issue.id
                assert (await service.issue_certificate(session,actor,settings,**(args|{"request_key":"second"}))).id==issue.id
                await session.commit()
                assert await session.scalar(select(func.count()).select_from(PortfolioItem)) == 1
                pdf=build_certificate_pdf(issue.snapshot,number=issue.document_number,issued_at=issue.issued_at)
                assert pdf.startswith(b"%PDF") and len(pdf)>5000
                old_name=issue.snapshot['full_name']
                target.first_name="Изменено";await session.flush()
                assert issue.snapshot['full_name']==old_name
                grant.is_active=False;await session.flush()
                with pytest.raises(PermissionError):
                    await service.revoke_certificate(session,actor,settings,issue.id,"Исправление имени")
                grant.is_active=True;await session.flush()
                await service.revoke_certificate(session,actor,settings,issue.id,"Исправление имени")
                item=await session.get(PortfolioItem,issue.portfolio_item_id)
                assert item.status=="revoked"
                for action in (career_service.update_item(session,item,title="Подмена"),
                               career_service.attach_file(session,item,file_id="fake",file_name="a"),
                               career_service.request_verification(session,item)):
                    with pytest.raises(ValueError,match="verified_item_locked"):
                        await action
                assert (await service.issue_certificate(session,actor,settings,**args)).status=="revoked"
                new_snapshot=await service.certificate_snapshot(session,target.id,event.id,snapshot['signatory'])
                new=await service.issue_certificate(session,actor,settings,**(args|{"request_key":"third",
                    "expected_hash":service.snapshot_hash(new_snapshot)}))
                assert new.revision==2 and new.id!=issue.id
                assert await session.scalar(select(func.count()).select_from(CertificateIssue)) == 2
                await session.commit()
                # Personal export includes the registry; approved erasure keeps
                # document numbers but removes holder PII without breaking FKs.
                from app.services import data_rights_service
                await session.refresh(target, attribute_names=['departments','directions'])
                exported=await data_rights_service.export_user_data(session,target)
                assert len(exported['issued_certificates'])==2
                assert exported['issued_certificates'][-1]['snapshot']['full_name']==new_snapshot['full_name']
                deletion=await data_rights_service.request_deletion(session,target,None)
                await data_rights_service.fulfill_deletion_request(session,deletion,admin=actor,approve=True)
                await session.commit()
                await session.refresh(new)
                assert new.status=='revoked' and new.snapshot['full_name']=='Удалённый пользователь'
                assert new.snapshot['signatory']=='ЭРА'
                assert (await session.get(PortfolioItem,new.portfolio_item_id)).status=='revoked'

        finally:
            await engine.dispose()
    asyncio.run(scenario())


def test_certificate_download_requires_owner_and_preserves_revoked_label():
    app=FastAPI();app.include_router(router,prefix="/api/v1")
    snapshot=dict(full_name="Имя",event_title="Событие",event_date="2026-10-19",signatory="Подписант",template_version="era-event-v1")
    issue=SimpleNamespace(user_id=2,status="issued",snapshot=snapshot,issued_at=None,document_number="ERA-CERT-000001")
    session=SimpleNamespace(get=AsyncMock(return_value=issue))
    async def override():yield session
    app.dependency_overrides[get_session]=override
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=1)
    client=TestClient(app)
    assert client.get('/api/v1/career/certificates/1.pdf').status_code==404
    issue.user_id=1;issue.status='revoked'
    response=client.get('/api/v1/career/certificates/1.pdf')
    assert response.status_code==200 and response.content.startswith(b'%PDF')
    assert 'no-store' in response.headers['cache-control']


def test_old_certificate_click_cannot_issue_without_current_preview():
    from app.handlers.certificates import confirm
    from unittest.mock import patch
    async def scenario():
        call=SimpleNamespace(answer=AsyncMock(),message=SimpleNamespace(answer=AsyncMock()), data='cert:confirm:'+'a'*32)
        state=SimpleNamespace(get_data=AsyncMock(return_value={}))
        with patch('app.handlers.certificates.allowed',new=AsyncMock(return_value=True)), patch.object(service,'issue_certificate',new=AsyncMock()) as issue:
            await confirm(call,None,None,None,state)
            issue.assert_not_awaited()
            assert 'устарел' in call.message.answer.call_args.args[0]
    asyncio.run(scenario())
