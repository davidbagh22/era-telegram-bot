import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, Broadcast, Department, Office, Task, TaskDelivery, User, UserDepartment, UserOffice
from app.database.system_models import NotificationDelivery
from app.handlers.leaders_native import native_leaders
from app.services import leaders_access_service as access, leaders_campaign_service as campaigns, leaders_workspace as work
from app.services.leadership_weekly_service import _send_cycle_reminder
from app.services.leaders_topics_service import setup_leaders_topics
from app.utils.constants import ApplicationStatus, Role


class LeadersWorkcenterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine=create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions=async_sessionmaker(self.engine,expire_on_commit=False)
        self.settings=Settings(bot_token='0000000000:CITESTTOKEN',admin_ids=[1001],leaders_chat_id=-100777,general_chat_id=-100888)
        async with self.sessions() as session:
            a=User(telegram_id=1001,first_name='Admin',role=Role.ADMIN,application_status=ApplicationStatus.APPROVED)
            h=User(telegram_id=1002,first_name='Head',role=Role.HEAD,application_status=ApplicationStatus.APPROVED)
            m=User(telegram_id=1003,first_name='Member',role=Role.LEADER,application_status=ApplicationStatus.APPROVED)
            o=User(telegram_id=1004,first_name='Other',role=Role.LEADER,application_status=ApplicationStatus.APPROVED)
            p=User(telegram_id=1005,first_name='Candidate',role=Role.PARTICIPANT,application_status=ApplicationStatus.APPROVED)
            dept=Department(name='Команда А');other=Department(name='Команда Б')
            session.add_all([a,h,m,o,p,dept,other]);await session.flush()
            session.add_all([UserDepartment(user_id=h.id,department_id=dept.id),UserDepartment(user_id=m.id,department_id=dept.id),UserDepartment(user_id=o.id,department_id=other.id)])
            session.add(AppSetting(key='leaders_forum:-100777:important', value='{"mode":"plain"}'))
            await session.commit()
            self.admin,self.head,self.member,self.other,self.candidate=a.id,h.id,m.id,o.id,p.id
            self.dept,self.other_dept=dept.id,other.id

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_legacy_community_offices_authorize_their_responsibility_and_expire(self):
        async with self.sessions() as session:
            deputy=await session.get(User,self.candidate)
            external=await session.get(Department,self.other_dept)
            external.name='Внешние связи'
            head=await session.get(User,self.head)
            session.add(UserDepartment(user_id=head.id,department_id=external.id))
            deputy_office=Office(title='Заместитель председателя',scope_type='community')
            head_office=Office(title='Руководитель внешних связей',scope_type='community')
            session.add_all([deputy_office,head_office]);await session.flush()
            a=UserOffice(user_id=deputy.id,office_id=deputy_office.id,appointed_by=self.admin)
            b=UserOffice(user_id=head.id,office_id=head_office.id,appointed_by=self.admin)
            session.add_all([a,b]);await session.commit()
            self.assertTrue(await access.executive(session,deputy,self.settings))
            self.assertEqual(await access.scopes(session,head,self.settings),{('department',external.id)})
            self.assertIn(deputy.id,{u.id for u in await work.roster(session,self.settings.leaders_chat_id)})
            # An explicit scoped override cannot become community-wide authority.
            a.scope_type='department';a.scope_id=self.dept
            await session.commit()
            self.assertFalse(await access.executive(session,deputy,self.settings))
            a.is_active=False;b.is_active=False
            await session.commit()
            self.assertFalse(await access.executive(session,deputy,self.settings))
            self.assertEqual(await access.scopes(session,head,self.settings),set())

    async def test_native_cancel_does_not_get_consumed_as_campaign_or_team_text(self):
        from aiogram.types import Chat, Message
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.storage.base import StorageKey
        from app.handlers.leaders_native import CampaignState, TeamState, cancel_native_flow, router
        storage=MemoryStorage()
        state=FSMContext(storage=storage,key=StorageKey(bot_id=1,chat_id=1,user_id=1))
        message=Message(message_id=1,date=datetime.now(timezone.utc),chat=Chat(id=1,type='private'),text='/cancel')
        handler=next(h for h in router.message.handlers if h.callback==cancel_native_flow)
        for value in (CampaignState.text, TeamState.search):
            await state.set_state(value)
            self.assertTrue((await handler.check(message,raw_state=await state.get_state(),bot=AsyncMock()))[0])
        output=AsyncMock()
        await cancel_native_flow(output,state)
        self.assertIsNone(await state.get_state())
        await storage.close()

    async def test_leader_status_is_not_management_and_head_is_scoped(self):
        async with self.sessions() as session:
            member=await session.get(User,self.member);head=await session.get(User,self.head)
            self.assertFalse(await work.can_create_any(session,member,self.settings))
            self.assertTrue(await work.can_create_any(session,head,self.settings))
            with self.assertRaises(ValueError):
                await work.create_task(session,self.settings,member,title='Unexpected rights')
            with self.assertRaises(ValueError):
                await work.create_task(session,self.settings,head,title='Outside scope',department_id=self.other_dept)
            with self.assertRaises(ValueError):
                await work.create_task(session,self.settings,head,title='Wrong person',department_id=self.dept,assignee_id=self.other)
            task=await work.create_task(session,self.settings,head,title='Inside scope',department_id=self.dept,assignee_id=self.member)
            await session.commit()
            self.assertEqual(task.department_id,self.dept)
            self.assertFalse(await work.can_manage_task(session,task,member,self.settings))
            head.is_archived=True
            self.assertFalse(await work.can_manage_task(session,task,head,self.settings))

    async def test_task_confirmation_is_idempotent_and_result_reward_is_once(self):
        async with self.sessions() as session:
            admin=await session.get(User,self.admin);member=await session.get(User,self.member)
            task=await work.create_task(session,self.settings,admin,title='Result',request_key='request-111',points=0)
            await session.commit()
            again=await work.create_task(session,self.settings,admin,title='Result',request_key='request-111',points=0)
            self.assertEqual(task.id,again.id)
            self.assertEqual(await session.scalar(select(func.count()).select_from(TaskDelivery)),1)
            await work.claim_task(session,task,member)
            replay=await work.create_task(session,self.settings,admin,title='Result',request_key='request-111',points=0)
            self.assertEqual(replay.id,task.id)
            self.assertEqual(replay.assignee_id,member.id)
            with self.assertRaises(ValueError):
                await work.create_task(session,self.settings,admin,title='Changed',request_key='request-111',points=0)
            await work.change_task(session,self.settings,task,member,'start')
            await work.change_task(session,self.settings,task,member,'submit',('Done','document-id'))
            await session.commit()
            with self.assertRaises(ValueError):
                await work.change_task(session,self.settings,task,member,'accept')
            await work.change_task(session,self.settings,task,admin,'return','Please improve')
            await work.change_task(session,self.settings,task,member,'submit',('Improved','file-2'))
            await work.change_task(session,self.settings,task,admin,'accept')
            await session.commit()
            self.assertEqual(task.status,'completed')
            with self.assertRaises(ValueError):
                await work.change_task(session,self.settings,task,admin,'return','Old button')

    async def test_addressed_task_can_be_declined_and_another_person_cannot_decline_it(self):
        async with self.sessions() as session:
            admin=await session.get(User,self.admin);member=await session.get(User,self.member);other=await session.get(User,self.other)
            task=await work.create_task(session,self.settings,admin,title='Offer',assignee_id=member.id)
            await session.commit()
            self.assertIs(work.meta(task)['accepted'],False)
            with self.assertRaises(ValueError): await work.change_task(session,self.settings,task,other,'decline')
            await work.change_task(session,self.settings,task,member,'decline')
            self.assertIsNone(task.assignee_id)
            await work.claim_task(session,task,other)
            await work.change_task(session,self.settings,task,other,'start')
            with self.assertRaises(ValueError): await work.change_task(session,self.settings,task,other,'decline')

    async def test_role_assignment_is_versioned_and_preserves_management_boundary(self):
        async with self.sessions() as session:
            admin=await session.get(User,self.admin);head=await session.get(User,self.head)
            with self.assertRaises(PermissionError):
                await access.set_leader(session,self.settings,head,self.candidate,enabled=True,expected_role='participant')
            target=await access.set_leader(session,self.settings,admin,self.candidate,enabled=True,expected_role='participant')
            await session.commit()
            self.assertEqual(target.role,'leader')
            self.assertFalse(await work.can_create_any(session,target,self.settings))
            with self.assertRaises(ValueError):
                await access.set_leader(session,self.settings,admin,self.candidate,enabled=False,expected_role='participant')
            await access.set_leader(session,self.settings,admin,self.candidate,enabled=False,expected_role='leader')
            self.assertEqual(target.role,'activist')
            with self.assertRaises(ValueError):
                await access.set_leader(session,self.settings,admin,self.admin,enabled=False,expected_role='admin')

    async def test_native_entry_does_not_redirect_to_mini_app(self):
        message=SimpleNamespace(chat=SimpleNamespace(id=1001,type='private'),answer=AsyncMock())
        async with self.sessions() as session:
            await native_leaders(message,SimpleNamespace(clear=AsyncMock()),await session.get(User,self.admin),self.settings,session,AsyncMock())
        text=message.answer.await_args.args[0]
        self.assertIn('Лидеры ЭРА',text)
        buttons=message.answer.await_args.kwargs['reply_markup'].inline_keyboard
        self.assertTrue(any(b.callback_data=='wc:new' for row in buttons for b in row))
        self.assertFalse(any(b.web_app for row in buttons for b in row))

    async def test_sent_pulse_reminder_survives_copy_change_without_duplicate_or_conflict(self):
        async with self.sessions() as session:
            user=await session.get(User,self.member)
            key=f'leadership-pulse-cycle:99:first:{user.id}'
            session.add(NotificationDelivery(delivery_key=key,chat_id=user.telegram_id,notification_type='pulse',status='sent',payload_hash='legacy-hash',attempt_count=1))
            await session.commit()
            with patch('app.services.leadership_weekly_service.send_bot_notification',new=AsyncMock()) as send:
                for body in ('Old copy','New copy'):
                    result=await _send_cycle_reminder(session,AsyncMock(),self.settings,user=user,cycle=SimpleNamespace(id=99),stage='first',body=body,action=None)
                    self.assertTrue(result)
                send.assert_not_awaited()
            row=await session.scalar(select(NotificationDelivery).where(NotificationDelivery.delivery_key==key))
            self.assertEqual(row.attempt_count,1)
            self.assertEqual(row.payload_hash,'legacy-hash')

    async def test_unsent_reminder_freezes_copy_before_external_delivery(self):
        async with self.sessions() as session:
            user=await session.get(User,self.member)
            with patch('app.services.leadership_weekly_service.send_bot_notification',new=AsyncMock(return_value=False)) as send:
                for body in ('First saved text','Changed text'):
                    await _send_cycle_reminder(session,AsyncMock(),self.settings,user=user,cycle=SimpleNamespace(id=100),stage='final',body=body,action=None)
                self.assertEqual([c.kwargs['body'] for c in send.await_args_list],['First saved text','First saved text'])
            row=await session.scalar(select(AppSetting).where(AppSetting.key.like('pulse-reminder-snapshot:100:%')))
            self.assertEqual(json.loads(row.value)['body'],'First saved text')

    async def test_plain_chat_setup_is_reusable_without_forum_topics(self):
        bot=AsyncMock()
        bot.get_chat.return_value=SimpleNamespace(type='supergroup',is_forum=False)
        bot.get_me.return_value=SimpleNamespace(id=99,username='test_bot')
        bot.get_chat_member.return_value=SimpleNamespace(status='administrator',can_pin_messages=True)
        bot.send_message.return_value=SimpleNamespace(message_id=55)
        for _ in range(2):
            self.assertEqual((await setup_leaders_topics(bot,self.settings,self.sessions))['status'],'ready_plain')
        self.assertEqual(bot.send_message.await_count,1)
        bot.create_forum_topic.assert_not_awaited()
        self.assertEqual(bot.pin_chat_message.await_count,1)

    async def test_campaign_keeps_one_fixed_queue_and_scope_and_uncertain_send_is_not_replayed(self):
        async with self.sessions() as session:
            session.add(AppSetting(
                key='leaders_forum:-100777:tasks',
                value='{"mode":"plain","message_id":55,"message_state":"sent"}',
            ))
            await session.commit()
            admin=await session.get(User,self.admin);head=await session.get(User,self.head)
            with self.assertRaises(PermissionError):
                await campaigns.create(session,self.settings,head,body='Outside',request_key='scope',mode='dm',department_id=self.other_dept)
            with self.assertRaises(ValueError):
                await campaigns.create(session,self.settings,head,body='Scoped',request_key='scope',mode='group',department_id=self.dept)
            item=await campaigns.create(session,self.settings,admin,body='Hello',request_key='campaign-111',mode='group',acknowledge=True)
            await session.commit()
            again=await campaigns.create(session,self.settings,admin,body='Hello',request_key='campaign-111',mode='group',acknowledge=True)
            self.assertEqual(item.id,again.id)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Broadcast)),1)
            receipt=SimpleNamespace(sent=False,duplicate=False,status='uncertain',error_code='telegram_network',message_id=None)
            with patch('app.services.admin_broadcast_service.safe_send_once',new=AsyncMock(return_value=receipt)) as send:
                await campaigns.send(session,self.settings,AsyncMock(),item)
                self.assertEqual(item.status,'review_required')
                await campaigns.send(session,self.settings,AsyncMock(),item)
                self.assertEqual(send.await_count,1)
