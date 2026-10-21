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
from app.database.socials import SocialProfile
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

    async def complete_quick_form(self, *, user=None, photo=None):
        with patch.object(registration, 'is_channel_member', AsyncMock(return_value=True)):
            await registration.registration_start(self.call, self.state, self.bot, self.settings, user)
        assert await self.state.get_state() == RegistrationStates.full_name.state
        await registration.registration_full_name(self.message('Анна Тестова'), self.state)
        await registration.registration_age(self.message('17'), self.state)
        await registration.registration_country(self.message('Армения'), self.state)
        await registration.registration_region(self.message('Ереван'), self.state)
        await registration.registration_email(self.message('applicant@example.test'), self.state)
        await registration.registration_education(self.message('Университет'), self.state)
        await registration.registration_occupation(self.message('Студент'), self.state)
        await registration.registration_skills(self.message('Дизайн, тексты'), self.state)
        await self.state.update_data(selected_directions=['participate'])
        self.call.data = 'reg:dir:done'
        await registration.registration_directions(self.call, self.state)
        await registration.registration_experience(self.message('Помогал команде проекта'), self.state)
        self.call.data = 'reg:time:1-2'
        await registration.registration_available_time(self.call, self.state)
        self.call.data = 'reg:path:0'
        await registration.registration_desired_path(self.call, self.state)
        await registration.registration_motivation(self.message('Хочу создавать события'), self.state)
        await registration.registration_social_skip(self.call, self.state)
        assert await self.state.get_state() == RegistrationStates.profile_photo.state
        message = self.message(None)
        message.photo = [SimpleNamespace(file_id='small'), SimpleNamespace(file_id=photo or 'fixture-photo')]
        message.answer_photo = AsyncMock()
        await registration.registration_photo(message, self.state)
        message.answer_photo.assert_awaited_once_with(photo or 'fixture-photo', caption='Фото для анкеты', reply_markup=None)
        await registration.registration_review_ok(self.call, self.state)

    async def test_uploaded_photo_survives_submit_and_is_available_to_admin_card(self):
        await self.complete_quick_form(photo='registration-photo')
        with patch.object(registration, '_notify_admins_registration', AsyncMock()):
            async with self.sessions() as session:
                await registration.finish_registration(self.call, self.state, session, self.bot, self.settings)
        from app.services.admin_user_card import build_admin_user_card
        async with self.sessions() as session:
            user = await session.scalar(select(User))
            profile = await session.scalar(select(SocialProfile).where(SocialProfile.user_id == user.id))
            assert profile.photo_file_id == 'registration-photo'
            assert (await build_admin_user_card(session, user, mode='application')).photo_file_id == 'registration-photo'

    async def test_motivation_does_not_erase_existing_photo(self):
        await self.state.update_data(profile_photo_file_id='already-uploaded')
        message = self.message('Хочу участвовать')
        message.answer_photo = AsyncMock()
        await registration.registration_motivation(message, self.state)
        assert (await self.state.get_data())['profile_photo_file_id'] == 'already-uploaded'
        assert await self.state.get_state() == RegistrationStates.social_url.state
        self.call.message.answer_photo = AsyncMock()
        await registration.registration_social_skip(self.call, self.state)
        self.call.message.answer_photo.assert_awaited_once()

    async def test_full_form_and_resume_render_headings_and_escape_answers(self):
        # No global Bot parse mode: each formatted prompt must carry its own.
        await registration._begin_registration(self.call.message, self.state,
            Settings(bot_token='1234567890:test', feature_quick_registration='OFF'), 22)
        messages = [self.call.message]
        for handler, value in [
            (registration.registration_full_name, 'Анна & Тестова'),
            (registration.registration_age, '24'),
            (registration.registration_country, 'Армения'),
            (registration.registration_region, 'Ереван'),
            (registration.registration_email, 'applicant@example.test'),
            (registration.registration_education, 'Университет'),
            (registration.registration_occupation, 'Студент'),
            (registration.registration_skills, 'Дизайн, SMM'),
        ]:
            message = self.message(value)
            messages.append(message)
            await handler(message, self.state)
            await registration.registration_resume(self.call, self.state, self.settings)
        await self.state.update_data(selected_directions=['participate'])
        self.call.data = 'reg:dir:done'
        await registration.registration_directions(self.call, self.state)
        message = self.message('Помогать команде')
        messages.append(message)
        await registration.registration_experience(message, self.state)
        self.call.data = 'reg:time:1-2'
        await registration.registration_available_time(self.call, self.state)
        self.call.data = 'reg:path:0'
        await registration.registration_desired_path(self.call, self.state)
        await self.state.update_data(profile_photo_file_id='fixture-photo')
        self.call.message.answer_photo = AsyncMock()
        message = self.message('Новые друзья <и> опыт')
        messages.append(message)
        await registration.registration_motivation(message, self.state)
        await registration.registration_social_skip(self.call, self.state)
        assert await self.state.get_state() == RegistrationStates.review.state
        for message in messages:
            for sent in message.answer.await_args_list:
                if '<b>' in sent.args[0]:
                    assert sent.kwargs.get('parse_mode') == 'HTML'
        review = self.call.message.answer.await_args.args[0]
        assert 'Анна &amp; Тестова' in review
        assert 'Новые друзья &lt;и&gt; опыт' in review

    async def test_referral_entry_uses_current_form_and_keeps_invite_on_resume(self):
        from app.handlers import referrals
        for rollout in ['OFF', 'ALL']:
            await self.state.clear()
            self.settings.feature_quick_registration = rollout
            self.call.data = 'registration:ref:start:123456'
            with patch.object(referrals, 'validate_referral_code', AsyncMock(
                return_value=(SimpleNamespace(code='123456'), None))), patch.object(
                referrals, 'is_channel_member', AsyncMock(return_value=True)):
                await referrals.registration_start_with_referral(self.call, self.state, AsyncMock(),
                    self.bot, self.settings, None)
            assert await self.state.get_state() == RegistrationStates.full_name.state
            assert self.call.message.answer.await_args.kwargs['parse_mode'] == 'HTML'
            assert (await self.state.get_data())['referral_code'] == '123456'
        await self.state.set_state(RegistrationStates.first_name)
        await registration.registration_resume(self.call, self.state, self.settings)
        assert await self.state.get_state() == RegistrationStates.full_name.state
        assert (await self.state.get_data())['referral_code'] == '123456'

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

    async def test_old_quick_consent_cannot_submit_incomplete_form_or_erase_invite(self):
        await self.state.update_data(first_name='Анна', last_name='Тестова', age=24, email='fixture@example.test',
            referral_code='123456', consent_policy_version=CURRENT_POLICY_VERSION, registration_mode='quick')
        with patch.object(registration, 'create_user_from_registration', AsyncMock()) as create:
            async with self.sessions() as session:
                await registration.finish_registration(self.call, self.state, session, self.bot, self.settings)
            create.assert_not_awaited()
        assert await self.state.get_state() == RegistrationStates.education_work.state
        assert (await self.state.get_data())['referral_code'] == '123456'
        assert (await self.state.get_data())['email'] == 'fixture@example.test'

    async def test_photo_is_required_before_consent_even_from_an_old_review_button(self):
        await self.complete_quick_form()
        data=await self.state.get_data()
        data.pop('profile_photo_file_id')
        await self.state.set_data(data)
        await self.state.set_state(RegistrationStates.review)
        await registration.registration_review_ok(self.call,self.state)
        assert await self.state.get_state() == RegistrationStates.profile_photo.state
        assert (await self.state.get_data())['first_name'] == 'Анна'

    async def test_social_skip_preserves_existing_optional_contacts(self):
        await self.state.update_data(social_url='https://example.test/portfolio',phone='+37400000000',profile_photo_file_id='photo')
        self.call.message.answer_photo=AsyncMock()
        await registration.registration_motivation(self.message('Хочу помогать'),self.state)
        await registration.registration_social_skip(self.call,self.state)
        data=await self.state.get_data()
        assert data['social_url']=='https://example.test/portfolio'
        assert data['phone']=='+37400000000'
        assert data['profile_photo_file_id']=='photo'

    def test_long_unicode_review_keeps_all_answers_below_telegram_limit(self):
        import html
        from app.handlers.registration import _registration_review_text, _review_chunks
        data={'first_name':'Fixture','last_name':'Applicant','education_work':'&'*255,'occupation':'🧩'*255,
              'skills':['🧩'*100]*10,'experience':'🧩'*1200,'motivation':'<'*1200}
        text=_registration_review_text(data)
        chunks=_review_chunks(text)
        assert len(chunks)>1
        assert ''.join(chunk.replace('\n','') for chunk in chunks)==text.replace('\n','')
        for chunk in chunks:
            plain=html.unescape(chunk.replace('<b>','').replace('</b>',''))
            assert len(plain.encode('utf-16-le'))//2<=4096
            assert chunk.count('<b>')==chunk.count('</b>')

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
        await self.complete_quick_form(user=target, photo='replacement-photo')
        with patch.object(registration, '_notify_admins_registration', AsyncMock()) as notify:
            async with self.sessions() as session:
                await registration.finish_registration(self.call, self.state, session, self.bot, self.settings)
            assert notify.await_args.kwargs['notification_revision'] > 0
        async with self.sessions() as session:
            target = await session.scalar(select(User).where(User.telegram_id == 22))
            assert target.id == user_id and target.application_status == ApplicationStatus.PENDING
            assert target.first_name == 'Анна'
            profile = await session.scalar(select(SocialProfile).where(SocialProfile.user_id == target.id))
            assert profile.photo_file_id == 'replacement-photo'
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
