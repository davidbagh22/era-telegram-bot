import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.config import Settings
from app.database.base import Base
from app.database.community_verification_models import CommunityMemberIdentity
from app.database.models import AppSetting, PointTransaction, User
from app.repositories.users import get_user_by_telegram_id
from app.services.registration_reset_service import apply_registration_reset
from app.utils.constants import ApplicationStatus, Role


def test_reset_exact_identity_preserves_history_clears_only_target_fsm_and_never_repeats():
    async def scenario():
        engine=create_async_engine('sqlite+aiosqlite:///:memory:');storage=MemoryStorage()
        secret=Fernet.generate_key().decode()
        settings=Settings(bot_token='0000000000:TEST')
        try:
            async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
            factory=async_sessionmaker(engine,expire_on_commit=False)
            async with factory() as session:
                target=User(telegram_id=12345,first_name='Archived',role=Role.PARTICIPANT,application_status=ApplicationStatus.APPROVED,is_archived=True)
                other=User(telegram_id=23456,first_name='Other',application_status=ApplicationStatus.APPROVED)
                session.add_all([target,other]);await session.flush();tid=target.id
                session.add(PointTransaction(user_id=tid,points=50,reason='Historical'))
                now=datetime.now(timezone.utc)
                session.add(CommunityMemberIdentity(telegram_id=12345,user_id=tid,first_seen_at=now,last_seen_at=now))
                await session.commit()
            targetkey=StorageKey(bot_id=1,chat_id=12345,user_id=12345)
            otherkey=StorageKey(bot_id=1,chat_id=23456,user_id=23456)
            for key in (targetkey,otherkey):
                await storage.set_state(key,'RegistrationStates.email');await storage.set_data(key,{'email':'private'})
            command=json.dumps(dict(telegram_id=12345,expected_user_id=tid,request_id='reset-test-20261020'))
            assert await apply_registration_reset(settings,factory,storage,1,command=command,backup_key=secret)=='complete'
            async with factory() as session:
                assert await get_user_by_telegram_id(session,12345) is None
                old=await session.get(User,tid);assert old.is_archived and old.telegram_id<0
                assert await session.scalar(select(PointTransaction.points).where(PointTransaction.user_id==tid))==50
                row=await session.scalar(select(AppSetting).where(AppSetting.key=='registration-reset:reset-test-20261020'))
                assert row.value['status']=='complete' and 'email' not in json.dumps(row.value)
                snapshot=json.loads(Fernet(secret.encode()).decrypt(row.value['encrypted_snapshot'].encode()))
                assert snapshot['user']['telegram_id']==12345 and snapshot['fsm_data']['email']=='private'
            assert await storage.get_state(targetkey) is None and await storage.get_data(targetkey)=={}
            assert await storage.get_data(otherkey)=={'email':'private'}
            # The real registration entry can now start from its first field.
            from app.handlers.registration import registration_start
            call=SimpleNamespace(answer=AsyncMock(),data='registration:start',from_user=SimpleNamespace(id=12345),message=SimpleNamespace(answer=AsyncMock()))
            state=FSMContext(storage,targetkey)
            with patch('app.handlers.registration.is_channel_member',new=AsyncMock(return_value=True)):
                await registration_start(call,state,AsyncMock(),settings,None)
            assert (await state.get_state()) is not None
            async with factory() as session:
                new=User(telegram_id=12345,first_name='New',application_status=ApplicationStatus.PENDING)
                session.add(new);await session.commit();nid=new.id
            assert await apply_registration_reset(settings,factory,storage,1,command=command,backup_key=secret)=='already_complete'
            async with factory() as session:assert (await get_user_by_telegram_id(session,12345)).id==nid
        finally:
            await storage.close();await engine.dispose()
    asyncio.run(scenario())


def test_reset_refuses_unverified_target_id_and_admin():
    async def scenario():
        settings=Settings(bot_token='0000000000:TEST',admin_ids=[12345])
        command=json.dumps(dict(telegram_id=12345,expected_user_id=31,request_id='reset-test-20261020'))
        with pytest.raises(ValueError,match='protected'):
            await apply_registration_reset(settings,None,None,1,command=command,backup_key=Fernet.generate_key().decode())
    asyncio.run(scenario())
