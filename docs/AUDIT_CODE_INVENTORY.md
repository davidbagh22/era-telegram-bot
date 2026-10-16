# Code inventory: 16.10.2026

Статическое извлечение текущей ветки. Декларация обработчика или задания не доказывает фактическую доставку в production. Активный состав router определяется app/bot.py, scheduler — lifespan app/webapp.py.

## Модули

| Каталог | Python файлов | Назначение |
|---|---:|---|
| app/handlers | 92 | Telegram обработчики |
| app/services | 134 | Предметные сервисы |
| app/api | 60 | HTTP API |
| app/database | 23 | Модели/сессии БД |
| app/keyboards | 9 | Кнопки/меню |
| app/middlewares | 10 | Доступ и контекст |
| alembic/versions | 66 | Миграции |

## Команды и обработчики

| Файл / функция | Command-фильтр |
|---|---|
| app/handlers/admin/addons.py:admin_cancel_command | `router.message(Command('cancel'))` |
| app/handlers/admin/commands_ready.py:status_command | `router.message(Command('status'))` |
| app/handlers/admin/commands_ready.py:backup_command | `router.message(Command('backup'))` |
| app/handlers/admin/commands_ready.py:org_command | `router.message(Command('org'))` |
| app/handlers/admin/commands_ready.py:admin_users_command | `router.message(Command('admin_users'))` |
| app/handlers/admin/commands_ready.py:admin_events_command | `router.message(Command('admin_events'))` |
| app/handlers/admin/commands_ready.py:admin_projects_command | `router.message(Command('admin_projects'))` |
| app/handlers/admin/commands_ready.py:admin_partners_command | `router.message(Command('admin_partners'))` |
| app/handlers/admin/commands_ready.py:admin_tasks_command | `router.message(Command('admin_tasks'))` |
| app/handlers/admin/commands_ready.py:admin_rights_command | `router.message(Command('admin_rights'))` |
| app/handlers/admin/dashboard_block_a.py:admin_dashboard | `router.message(Command('admin'))` |
| app/handlers/admin/dashboard_block_a.py:applications_queue | `router.message(Command('applications'))` |
| app/handlers/admin/legacy_action_bridge.py:panel_launcher | `router.message(Command('panel'))` |
| app/handlers/admin/management_ready.py:panel_command | `router.message(Command('panel'))` |
| app/handlers/admin/panel.py:portfolio_add_command | `router.message(Command('portfolio'))` |
| app/handlers/admin/panel.py:addpoints_command | `router.message(Command('addpoints'))` |
| app/handlers/admin/panel.py:award_badge | `router.message(Command('awardbadge'))` |
| app/handlers/admin/panel.py:set_role | `router.message(Command('setrole'))` |
| app/handlers/admin/panel.py:set_status | `router.message(Command('setstatus'))` |
| app/handlers/admin/panel.py:set_setting | `router.message(Command('setsetting'))` |
| app/handlers/admin/surveys_analytics.py:surveys_command | `router.message(Command('admin_surveys'))` |
| app/handlers/admin/version_command.py:version_command | `router.message(Command('version'))` |
| app/handlers/chat.py:rules | `router.message(Command('rules'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:links | `router.message(Command('links'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:departments | `router.message(Command('departments'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:events_link | `router.message(Command('events'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:project_link | `router.message(Command('project'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:moderation_on | `router.message(Command('moderation_on'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:moderation_off | `router.message(Command('moderation_off'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat.py:moderation_status | `router.message(Command('moderation_status'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat_binding.py:bind_current_chat | `router.message(Command('bind'), ~F.chat.type.in_({'private'}))` |
| app/handlers/chat_unlock.py:unlock_general_chat | `router.message(Command('unlock_chat'), F.chat.type == 'private')` |
| app/handlers/emergency.py:group_start | `router.message(CommandStart(), F.chat.type != 'private')` |
| app/handlers/emergency.py:rescue_start | `router.message(StateFilter('*'), CommandStart(), F.chat.type == 'private')` |
| app/handlers/emergency.py:rescue_start | `router.message(StateFilter('*'), Command('menu'), F.chat.type == 'private')` |
| app/handlers/emergency.py:cancel_any | `router.message(StateFilter('*'), Command('cancel'), F.chat.type == 'private')` |
| app/handlers/era_game_room.py:game_menu | `router.message(Command('games', 'game'))` |
| app/handlers/leader/legacy_bridge.py:leader_launcher | `router.message(Command('leader'))` |
| app/handlers/leader/panel.py:leader_command | `router.message(Command('leader'))` |
| app/handlers/leader_chat_workcenter.py:connect_pulse_from_deep_link | `router.message(CommandStart(deep_link=True, magic=F.args == 'pulse_connect'), F.chat.type == 'private')` |
| app/handlers/leader_chat_workcenter.py:begin_group_task | `router.message(Command('task'), F.chat.type.in_({'group', 'supergroup'}))` |
| app/handlers/leaders_workspace.py:start_task | `router.message(Command('task'), F.chat.type.in_({'group', 'supergroup'}))` |
| app/handlers/participant/about.py:about_button | `router.message(Command('about'), F.chat.type == 'private')` |
| app/handlers/participant/cabinet.py:journey_button | `router.message(Command('journey'), F.chat.type == 'private')` |
| app/handlers/participant/cabinet.py:rating_button | `router.message(Command('rating'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:menu_command | `router.message(Command('menu'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:profile_command | `router.message(Command('profile'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:data_command | `router.message(Command('data'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:events_command | `router.message(Command('events'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:tasks_command | `router.message(Command('tasks'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:opportunities_command | `router.message(Command('opportunities'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:points_command | `router.message(Command('points'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:contact_command | `router.message(Command('contact'), F.chat.type == 'private')` |
| app/handlers/participant/commands_ready.py:help_command | `router.message(Command('help'), F.chat.type == 'private')` |
| app/handlers/participant/departments.py:departments_menu_button | `router.message(Command('team'), F.chat.type == 'private')` |
| app/handlers/participant/departments.py:departments_menu_button | `router.message(Command('departments'), F.chat.type == 'private')` |
| app/handlers/participant/development.py:vector_command | `router.message(Command('vector'), F.chat.type == 'private')` |
| app/handlers/participant/event_qr.py:qr_command | `router.message(Command('qr'), F.chat.type == 'private')` |
| app/handlers/participant/events_stability_block8.py:event_list_button | `router.message(Command('events'), F.chat.type == 'private')` |
| app/handlers/participant/navigation.py:navigation_command | `router.message(Command('navigation'), F.chat.type == 'private')` |
| app/handlers/participant/partners.py:partners_command | `router.message(Command('partners'))` |
| app/handlers/participant/point_transfer.py:start | `router.message(Command('give_points'))` |
| app/handlers/participant/projects.py:projects_menu_button | `router.message(Command('projects'), F.chat.type == 'private')` |
| app/handlers/participant/projects.py:projects_menu_button | `router.message(Command('project'), F.chat.type == 'private')` |
| app/handlers/participant/task_reply.py:tasks_command | `router.message(Command('tasks'), F.chat.type == 'private')` |
| app/handlers/pulse_private.py:start_pulse | `router.message(CommandStart(deep_link=True, magic=F.args == 'pulse_connect'), F.chat.type == 'private')` |
| app/handlers/pulse_private.py:start_pulse | `router.message(Command('pulse'), F.chat.type == 'private')` |
| app/handlers/referrals.py:referral_deep_link | `router.message(CommandStart(), F.text.regexp('^/start(?:@\\w+)?\\s+ref_\\d{6}\\s*$'))` |
| app/handlers/start.py:start | `router.message(CommandStart(), F.chat.type == 'private')` |
| app/handlers/start.py:start | `router.message(Command('menu'), F.chat.type == 'private')` |
| app/handlers/start.py:private_rules | `router.message(Command('rules'), F.chat.type == 'private')` |

## Планировщик

Выписаны все объявления add_job в scheduler_service.py и system_scheduler.py; дополнительные runtime overrides — app/webapp.py и app/main.py.

| Файл / функция | ID / триггер / параметры |
|---|---|
| app/services/scheduler_service.py:send_event_reminders | 'interval'; minutes=1, id='event-reminders' |
| app/services/scheduler_service.py:send_birthday_greetings | 'cron'; hour=10, minute=0, id='birthday-greetings' |
| app/services/scheduler_service.py:send_project_venue_reminders | 'interval'; minutes=15, id='project-venue-reminders' |
| app/services/scheduler_service.py:send_task_reminders | 'interval'; minutes=15, id='task-reminders' |
| app/services/scheduler_service.py:send_trajectory_campaign | 'interval'; minutes=15, id='trajectory-20261031-campaign' |
| app/services/scheduler_service.py:send_monthly_surveys | 'cron'; day=1, hour=11, minute=0, id='monthly-surveys' |
| app/services/scheduler_service.py:send_general_content_morning | 'cron'; hour=9, minute=0, id='general-content-morning' |
| app/services/scheduler_service.py:send_general_content_evening | 'cron'; hour=18, minute=0, id='general-content-evening' |
| app/services/scheduler_service.py:recover_general_content | 'interval'; minutes=30, id='general-content-recovery' |
| app/services/scheduler_service.py:send_weekly_message | 'cron'; day_of_week='mon', hour=10, minute=0, id=job_id |
| app/services/system_scheduler.py:run_system_diagnostics | 'interval'; minutes=15, id='system-heartbeat' |
| app/services/system_scheduler.py:run_system_diagnostics | 'interval'; hours=4, id='system-full-diagnostic' |
| app/services/system_scheduler.py:send_daily_system_summary | 'cron'; hour=9, minute=30, id='system-daily-summary' |
| app/services/system_scheduler.py:reconcile_vacancies_job | 'interval'; minutes=30, id='office-vacancy-reconciliation' |
| app/services/system_scheduler.py:send_configured_event_reminders | 'interval'; minutes=1, id='configured-event-reminders' |
| app/services/system_scheduler.py:deliver_pending_event_announcements | 'interval'; minutes=1, id='event-announcement-recovery' |
| app/services/system_scheduler.py:sync_event_wizard_tasks_job | 'interval'; minutes=1, id='event-wizard-task-sync' |
| app/services/system_scheduler.py:reconcile_project_scoring_job | 'interval'; minutes=1, id='project-scoring-reconciliation' |
| app/services/system_scheduler.py:process_task_squad_notifications | 'interval'; minutes=1, id='task-squad-notifications' |
| app/services/system_scheduler.py:reconcile_media_pipeline_job | 'interval'; minutes=1, id='media-content-pipeline-reconciliation' |
| app/services/system_scheduler.py:publish_due_channel_content | 'interval'; minutes=1, id='media-channel-publication' |
| app/services/system_scheduler.py:post_missing_media_task_cards | 'interval'; minutes=1, id='media-task-cards' |
| app/services/system_scheduler.py:process_media_chat_automation | 'interval'; minutes=1, id='media-chat-automation' |
| app/services/system_scheduler.py:run_reactivation_cycle | 'interval'; hours=1, id='participation-reactivation' |
| app/services/system_scheduler.py:complete_verification_campaigns_job | 'interval'; minutes=5, id='community-verification-expiry' |
| app/services/system_scheduler.py:send_monthly_development_reminders | 'cron'; hour=18, minute=0, id='my-vector-monthly-reminders' |
| app/services/system_scheduler.py:book_club_daily_job | 'cron'; hour=19, minute=0, timezone='Asia/Yerevan', id='book-club-daily' |
| app/services/system_scheduler.py:launch_catalog_job | 'interval'; minutes=30, id='public-catalog-launch' |
| app/services/system_scheduler.py:publish_literature_launch | 'interval'; minutes=5, id='literature-opening-recovery' |
| app/services/system_scheduler.py:publish_literature_channel_launch | 'interval'; minutes=5, id='literature-channel-opening' |
| app/services/system_scheduler.py:send_literature_admin_digest | 'cron'; hour=20, minute=0, id='literature-admin-digest' |
| app/services/system_scheduler.py:resume_broadcasts | 'interval'; minutes=1, id='admin-broadcast-resume' |
| app/services/system_scheduler.py:run_daily_public_content | 'interval'; minutes=5, id='era-daily-public-content' |
| app/services/system_scheduler.py:enforce_general_chat_writable | 'interval'; minutes=5, id='general-chat-writable-access' |
| app/services/system_scheduler.py:open_weekly_pulses_job | 'interval'; minutes=5, id='leadership-weekly-pulse-open' |
| app/services/system_scheduler.py:check_weekly_pulses_job | 'interval'; minutes=5, id='leadership-weekly-pulse-due' |
| app/services/system_scheduler.py:sync_leaders_task_cards | 'interval'; minutes=1, id='leaders-task-card-sync' |
| app/services/system_scheduler.py:setup_general_topics | 'interval'; minutes=5, id='general-forum-setup' |
| app/services/system_scheduler.py:expire_game_rooms | 'interval'; minutes=1, id='era-games-expiry' |
| app/services/system_scheduler.py:publish_games_launch | 'interval'; minutes=5, id='era-games-launch' |
| app/services/system_scheduler.py:publish_directions_announcement | 'interval'; minutes=5, id='directions-one-time-announcement' |
| app/services/system_scheduler.py:setup_leaders_topics | 'interval'; minutes=5, id='leaders-forum-setup' |
| app/services/system_scheduler.py:archive_due_cycles | 'interval'; minutes=5, id='pulse-weekly-archive' |
| app/main.py:run_daily_channel_content | 'interval'; minutes=5, id='era-daily-channel-content' |

## Кнопки и действующие модели

Кнопки находятся в app/keyboards/ и рядом с обработчиками; динамические callback_data и payload проверяются runtime тестами. Таблицы production и точные количества вынесены в AUDIT_PRODUCTION_COUNTS_2026_10_16.md.

## TODO/FIXME

Не каждый TODO — блокирующий дефект; ниже только расположение маркеров, без неподтверждённых выводов о работоспособности.

