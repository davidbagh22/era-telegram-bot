from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, ConsentLog, Department, Direction, User, UserDepartment, UserDirection
from app.handlers import emergency, registration
from app.services.application_review_service import reject_application
from app.services.consent_service import CURRENT_POLICY_VERSION
from app.states.registration import RegistrationStates
from app.utils.constants import ApplicationStatus


class RegistrationCompletionTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test', feature_quick_registration='ALL')
        self.state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=22, user_id=22))
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.call = SimpleNamespace(answer=AsyncMock(), data='registration:start',
                                    from_user=SimpleNamespace(id=22, username='applicant'),
                                    message=SimpleNamespace(answer=AsyncMock()))

    async def asyncTearDown(self):
        await self.engine.dispose()

    def message(self, text):
        return SimpleNamespace(text=text, from_user=self.call.from_user, answer=AsyncMock())

    async def complete_quick_form(self, *, user=None):
        with patch.object(registration, 'is_channel_member', AsyncMock(return_value=True)):
            await registration.registration_start(self.call, self.state, self.bot, self.settings, user)
        assert await self.state.get_state() == RegistrationStates.mode.state
        self.call.data = 'reg:mode:quick'
        await registration.registration_mode(self.call, self.state, self.settings, user)
        await registration.registration_full_name(self.message('Анна Тестова'), self.state)
        await registration.registration_age(self.message('17'), self.state)
        await registration.registration_country(self.message('Армения'), self.state)
        await registration.registration_region(self.message('Ереван'), self.state)
        await registration.registration_email(self.message('applicant@example.test'), self.state)
        assert await self.state.get_state() == RegistrationStates.review.state
        await registration.registration_review_ok(self.call, self.state)

    async def test_quick_flow_creates_one_pending_user_with_explicit_consent(self):
        await self.complete_quick_form()
        data = await self.state.get_data()
        with patch.object(registration, '_notify_admins_registration', AsyncMock()) as notify:
            async with self.sessions() as session:
                await registration.finish_registration(self.call, self.state, session, self.bot, self.settings)
            # Replay the same consent update after process/session replacement.
            await self.state.set_data(data)
            async with self.sessions() as session:
                await registration.finish_registration(self.call, self.state, session, self.bot, self.settings)
            assert notify.await_count == 1
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 1
            user = await session.scalar(select(User))
            assert user.application_status == ApplicationStatus.PENDING and user.age == 17
            assert user.first_name == 'Анна' and user.email == 'applicant@example.test'
            assert user.personal_data_consent
            assert await session.scalar(select(func.count()).select_from(ConsentLog)) == 1

    async def test_no_consent_creates_no_profile(self):
        await self.complete_quick_form()
        await registration.no_consent(self.call, self.state)
        assert await self.state.get_state() is None
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 0

    async def test_start_preserves_registration_progress_and_resumes_saved_question(self):
        await self.state.set_state(RegistrationStates.email)
        await self.state.update_data(first_name='Анна', age=17)
        message = self.message('/start')
        await emergency.rescue_start(message, self.bot, None, self.settings, self.state, None)
        assert await self.state.get_state() == RegistrationStates.email.state
        assert (await self.state.get_data())['first_name'] == 'Анна'
        await registration.registration_resume(self.call, self.state, self.settings)
        assert 'email' in self.call.message.answer.await_args.args[0].lower()

    async def test_reapplication_preserves_id_and_rejection_history_and_is_not_autoapproved(self):
        async with self.sessions() as session:
            target = User(telegram_id=22, first_name='Старое имя', application_status=ApplicationStatus.PENDING)
            session.add(target)
            await session.flush()
            await reject_application(session, target, actor_id=None, comment='Исходное решение')
            await session.commit()
            user_id = target.id
        self.call.data = 'registration:reapply'
        await self.complete_quick_form(user=target)
        with patch.object(registration, '_notify_admins_registration', AsyncMock()) as notify:
            async with self.sessions() as session:
                await registration.finish_registration(self.call, self.state, session, self.bot, self.settings)
            assert notify.await_args.kwargs['notification_revision'] > 0
        async with self.sessions() as session:
            target = await session.scalar(select(User).where(User.telegram_id == 22))
            assert target.id == user_id and target.application_status == ApplicationStatus.PENDING
            assert target.first_name == 'Анна'
            reason = await session.scalar(select(AuditLog).where(AuditLog.action == 'user.rejected'))
            assert reason.new_value['comment'] == 'Исходное решение'
            resubmission = await session.scalar(select(AuditLog).where(AuditLog.action == 'user.resubmitted'))
            assert resubmission.old_value == {'application_status': ApplicationStatus.REJECTED}

    async def test_forged_resubmission_cannot_change_approved_or_blocked_profile(self):
        from app.repositories.users import resubmit_user_registration
        async with self.sessions() as session:
            target = User(telegram_id=22, first_name='Original', application_status=ApplicationStatus.APPROVED)
            session.add(target)
            await session.commit()
            result, changed = await resubmit_user_registration(session, telegram_id=22, username='other',
                data={'first_name': 'Changed', 'consent_policy_version': CURRENT_POLICY_VERSION})
            assert not changed and result.first_name == 'Original'
            target.application_status = ApplicationStatus.REJECTED
            target.is_blocked = True
            await session.commit()
            _, changed = await resubmit_user_registration(session, telegram_id=22, username='other', data={})
            assert not changed

    async def test_quick_resubmission_preserves_uncollected_interests_and_membership_status(self):
        from app.repositories.users import resubmit_user_registration
        async with self.sessions() as session:
            department = Department(name='Test department')
            direction = Direction(name='Test direction', department=department)
            target = User(telegram_id=22, first_name='Original', application_status=ApplicationStatus.REJECTED,
                          departments=[UserDepartment(department=department, status='active')],
                          directions=[UserDirection(direction=direction, status='active')])
            session.add(target)
            await session.commit()
            old_department_id, old_direction_id = target.departments[0].id, target.directions[0].id
            await resubmit_user_registration(session, telegram_id=22, username='same',
                data={'first_name': 'Changed', 'consent_policy_version': CURRENT_POLICY_VERSION})
            await session.commit()
        async with self.sessions() as session:
            result = await session.get(User, target.id)
            assert result.departments[0].id == old_department_id and result.departments[0].status == 'active'
            assert result.directions[0].id == old_direction_id and result.directions[0].status == 'active'

    async def test_quick_mode_is_flagged_and_empty_tester_list_never_uses_other_feature_ids(self):
        self.settings.feature_quick_registration = 'TESTERS'
        self.settings.quick_registration_tester_ids = []
        self.settings.feature_tester_ids = [22]
        assert not registration._quick_enabled(self.settings, 22)
