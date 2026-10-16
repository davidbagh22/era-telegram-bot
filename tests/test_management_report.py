import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, PermissionGrant, User, UserQuestion
from app.database.system_models import BackupHistory, NotificationDelivery, SystemDiagnosticRun
from app.services.admin_analytics_service import (build_management_report, management_report_text,
    management_report_recipients, send_management_reports)
from app.services.excel_report_service import management_summary_workbook
from app.utils.constants import ApplicationStatus, Role


class ManagementReportTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test-token', feature_management_reports='ALL')
        self.now = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)  # 09:00 Moscow
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=10)))
        self.factory_patch = patch('app.services.notification_service._session_factory', return_value=self.sessions)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        async with self.sessions() as session:
            admin = User(telegram_id=11, first_name='Admin private', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED,
                         created_at=self.now-timedelta(days=2), phone='PRIVATE-PHONE')
            member = User(telegram_id=22, first_name='Member private', application_status=ApplicationStatus.APPROVED,
                          created_at=self.now-timedelta(hours=1))
            session.add_all([admin, member])
            await session.flush()
            self.admin_id, self.member_id = admin.id, member.id
            session.add(UserQuestion(user_id=member.id, text='PRIVATE QUESTION', status='new', created_at=self.now-timedelta(hours=25)))
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_report_is_sent_at_moscow_time_once_even_when_metrics_change(self):
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now-timedelta(minutes=1))
        self.bot.send_message.assert_not_awaited()
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now)
        async with self.sessions() as session:
            session.add(User(telegram_id=33, first_name='Later', application_status=ApplicationStatus.PENDING))
            await session.commit()
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now+timedelta(hours=5))
        self.bot.send_message.assert_awaited_once()
        text = self.bot.send_message.await_args.args[1]
        assert '09:00 МСК' in text and 'Обращения: ждут 1 · дольше 24 ч 1' in text
        assert 'PRIVATE' not in text and 'Admin private' not in text and 'Member private' not in text
        async with self.sessions() as session:
            deliveries = (await session.scalars(select(NotificationDelivery))).all()
            assert len(deliveries) == 1 and deliveries[0].delivery_key == 'daily:2026-10-16:11'
            assert deliveries[0].status == 'sent' and deliveries[0].attempt_count == 1

    async def test_missing_game_health_backup_data_are_not_reported_as_zero_or_healthy(self):
        async with self.sessions() as session:
            metrics = await build_management_report(session, now=self.now)
        assert metrics['games_completed'] is None and metrics['game_players'] is None
        assert metrics['health'] == 'нет данных' and metrics['scheduler'] == 'нет данных'
        text = management_report_text(metrics)
        assert 'игроков не измеряется · завершено не измеряется' in text
        assert 'Сравнение с предыдущим периодом: нет данных' in text
        assert 'Проверить резервное копирование' in text

    async def test_recipients_require_global_permission_and_blocked_profiles_are_excluded(self):
        async with self.sessions() as session:
            session.add(PermissionGrant(user_id=self.member_id, permission='analytics.view', scope_type='department', scope_id=1, granted_by=self.admin_id))
            await session.commit()
            assert await management_report_recipients(session, self.settings) == {11}
            session.add(PermissionGrant(user_id=self.member_id, permission='analytics.view', scope_type='global', scope_id=0, granted_by=self.admin_id))
            await session.commit()
            assert await management_report_recipients(session, self.settings) == {11, 22}
            user = await session.get(User, self.member_id)
            user.is_blocked = True
            await session.commit()
            assert await management_report_recipients(session, self.settings) == {11}

    async def test_testers_and_configured_recipients_cannot_expand_permissions(self):
        self.settings.feature_management_reports = 'TESTERS'
        self.settings.management_report_recipient_ids = [11, 22, 99]
        async with self.sessions() as session:
            assert await management_report_recipients(session, self.settings) == {11}
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now)
        assert self.bot.send_message.await_args.args[0] == 11

    async def test_daily_weekly_monthly_have_separate_stable_period_keys(self):
        now = datetime(2026, 6, 1, 6, tzinfo=timezone.utc)  # Monday and first of month
        await send_management_reports(self.bot, self.settings, self.sessions, now=now)
        await send_management_reports(self.bot, self.settings, self.sessions, now=now+timedelta(hours=1))
        assert self.bot.send_message.await_count == 3
        async with self.sessions() as session:
            keys = set((await session.scalars(select(NotificationDelivery.delivery_key))).all())
            assert keys == {'daily:2026-06-01:11', 'weekly:2026-06-01:11', 'monthly:2026-06-01:11'}
            row = await session.scalar(select(AppSetting).where(AppSetting.key == 'management-report:monthly:2026-06-01'))
            metrics = json.loads(row.value)['metrics']
            assert metrics['period_start'] == '2026-04-30T21:00:00+00:00'
            assert metrics['period_end'] == '2026-05-31T21:00:00+00:00'

    async def test_previous_report_is_compared_without_republishing_it(self):
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now-timedelta(days=1))
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now)
        assert 'Участников к предыдущему отчёту: +0' in self.bot.send_message.await_args.args[1]
        assert self.bot.send_message.await_count == 2

    async def test_excel_contains_aggregates_and_preserves_unknown_values(self):
        async with self.sessions() as session:
            metrics = await build_management_report(session, now=self.now)
        workbook = load_workbook(BytesIO(management_summary_workbook(metrics)))
        values = dict(list(workbook.active.values)[1:])
        assert values['Участников'] == 2
        assert values['Завершено игр (новый учёт)'] == 'не измеряется'
        assert 'PRIVATE' not in str(values)

    async def test_manual_report_callback_rejects_forged_participant_access(self):
        from app.handlers.admin.commands_ready import management_report_action
        call = SimpleNamespace(from_user=SimpleNamespace(id=22), answer=AsyncMock(), data='admin:management:refresh')
        async with self.sessions() as session:
            member = await session.get(User, self.member_id)
            await management_report_action(call, member, self.settings, session)
        call.answer.assert_awaited_once_with('Доступ к отчёту отсутствует.', show_alert=True)
        self.bot.send_message.assert_not_awaited()

    async def test_fresh_system_and_verified_restore_are_reported_as_observed(self):
        async with self.sessions() as session:
            session.add(SystemDiagnosticRun(run_type='heartbeat', status='ok', score=100, checks_json=[], created_at=self.now-timedelta(minutes=5)))
            session.add(BackupHistory(backup_key='verified', status='success', restore_verified_at=self.now-timedelta(hours=1)))
            await session.commit()
            metrics = await build_management_report(session, now=self.now)
        assert metrics['health'] == 'ok' and metrics['scheduler'] == 'работает'
        assert metrics['backup'] == 'восстановление проверено'
