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
        assert self.bot.send_message.await_count == 1
        text = next(c.args[1] for c in self.bot.send_message.await_args_list if 'Итоги за сутки' in c.args[1])
        assert '09:00 МСК' in text and 'Обращения: ждут 1 · дольше 24 ч 1' in text
        assert 'PRIVATE' not in text and 'Admin private' not in text and 'Member private' not in text
        async with self.sessions() as session:
            deliveries = (await session.scalars(select(NotificationDelivery))).all()
            assert len(deliveries) == 1
            assert any(d.delivery_key == 'daily:2026-10-16:11' for d in deliveries)
            assert all(d.status == 'sent' and d.attempt_count == 1 for d in deliveries)

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

    async def test_one_daily_issue_even_on_monday_and_first_day_of_month(self):
        now = datetime(2026, 6, 1, 6, tzinfo=timezone.utc)
        await send_management_reports(self.bot, self.settings, self.sessions, now=now)
        await send_management_reports(self.bot, self.settings, self.sessions, now=now+timedelta(hours=1))
        assert self.bot.send_message.await_count == 1
        async with self.sessions() as session:
            keys = set((await session.scalars(select(NotificationDelivery.delivery_key))).all())
            assert keys == {'daily:2026-06-01:11'}
            snapshot_keys = set((await session.scalars(select(AppSetting.key).where(AppSetting.key.like('management-report:%')))).all())
            assert snapshot_keys == {'management-report:daily:2026-06-01'}

    async def test_previous_report_is_compared_without_republishing_it(self):
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now-timedelta(days=1))
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now)
        assert 'Участников к предыдущему отчёту: +0' in self.bot.send_message.await_args.args[1]
        assert self.bot.send_message.await_count == 2

    async def test_restart_recovers_only_today_without_weekly_monthly_backfill(self):
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now)
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now+timedelta(hours=3))
        async with self.sessions() as session:
            keys = set((await session.scalars(select(NotificationDelivery.delivery_key))).all())
            assert keys == {'daily:2026-10-16:11'}
        assert self.bot.send_message.await_count == 1

    async def test_period_before_game_measurement_is_unknown_not_zero(self):
        async with self.sessions() as session:
            session.add(AppSetting(key='game-result:later', value=json.dumps({
                'finished_at': self.now.isoformat(), 'participants': [22]})))
            await session.commit()
            metrics = await build_management_report(session, now=self.now,
                period_start=self.now-timedelta(days=14), period_end=self.now-timedelta(days=7))
        assert metrics['games_completed'] is None and metrics['game_players'] is None

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


    async def test_health_freshness_and_latest_backup_failure_are_visible(self):
        async with self.sessions() as session:
            session.add(SystemDiagnosticRun(run_type='full', status='ok', score=100, checks_json=[],
                                            created_at=self.now-timedelta(minutes=5)))
            session.add(SystemDiagnosticRun(run_type='heartbeat', status='ok', score=100, checks_json=[],
                                            created_at=self.now-timedelta(hours=2)))
            session.add(BackupHistory(backup_key='previous-good', status='success',
                                      completed_at=self.now-timedelta(hours=2), restore_verified_at=self.now-timedelta(hours=2),
                                      created_at=self.now-timedelta(hours=2), size_bytes=1048576))
            session.add(BackupHistory(backup_key='latest-failed', status='failed',
                                      completed_at=self.now-timedelta(minutes=5), created_at=self.now-timedelta(minutes=5)))
            await session.commit()
            metrics = await build_management_report(session, now=self.now)
        text = management_report_text(metrics)
        assert metrics['health_fresh'] is True
        assert metrics['scheduler'] == 'нет свежего heartbeat'
        assert '🩺 Здоровье бота' in text and '💾 Резервная копия' in text
        assert 'Последняя попытка: ошибка' in text and 'Размер копии: 1.00 МБ' in text
        assert 'Проверить резервное копирование' in text
        assert 'Проверить работу планировщика' in text

    async def test_old_healthy_snapshot_is_not_presented_as_current_health(self):
        async with self.sessions() as session:
            session.add(SystemDiagnosticRun(run_type='heartbeat', status='ok', score=100, checks_json=[],
                                            created_at=self.now-timedelta(hours=2)))
            await session.commit()
            metrics = await build_management_report(session, now=self.now)
        text = management_report_text(metrics)
        assert '🟢 Состояние: в норме' not in text
        assert 'нет свежей проверки' in text and '16.10.2026 07:00 МСК' in text

    async def test_manual_statistics_does_not_create_a_second_automatic_issue(self):
        from app.handlers.admin.commands_ready import management_report_command
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now)
        message = SimpleNamespace(from_user=SimpleNamespace(id=11), answer=AsyncMock())
        async with self.sessions() as session:
            admin = await session.get(User, self.admin_id)
            await management_report_command(message, admin, self.settings, session)
            await management_report_command(message, admin, self.settings, session)
        assert message.answer.await_count == 2
        await send_management_reports(self.bot, self.settings, self.sessions, now=self.now+timedelta(hours=2))
        assert self.bot.send_message.await_count == 1

    async def test_separate_literature_digest_is_folded_into_the_daily_summary(self):
        from app.services.literature_analytics_service import send_literature_admin_digest
        await send_literature_admin_digest(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_not_awaited()
        async with self.sessions() as session:
            metrics = await build_management_report(session, now=self.now)
        assert 'Литература, всего:' in management_report_text(metrics)


    async def test_leisure_navigation_does_not_create_a_missing_forum_topic(self):
        from app.handlers.era_leisure import _markup
        settings = Settings(bot_token="1234567890:test-token", feature_games="ALL", general_chat_id=-10042)
        bot = SimpleNamespace(get_chat=AsyncMock(), create_forum_topic=AsyncMock())
        with patch('app.services.general_topics_service._session_factory', return_value=self.sessions):
            markup = await _markup(bot, settings, 11)
        assert not any(button.url for row in markup.inline_keyboard for button in row)
        bot.get_chat.assert_not_awaited()
        bot.create_forum_topic.assert_not_awaited()
