## Активный этап · 21.10.2026

Analytics 2.0: `docs/ANALYTICS_V2_SPEC.md`; реализация `telegram_analytics_service.py` / `admin_analytics_v2_service.py`, таблицы `telegram_analytics.py`, миграция0064, update/send middleware, admin API v2, `telegram_analytics_export.py`, `AdminDashboardScreen.tsx`. Регистрация+карточка — следующий отдельный этап, без сброса старых заявок. Фактические проверки/ограничения — в верхнем checkpoint `AI_TASK_STATE.md`.

# Карта точечной работы ЭРА

Актуальный checkpoint: docs/AI_TASK_STATE.md. Сначала сверять фактический SHA; не повторять reset/релизы. Исторические сведения ниже не заменяют live-проверку.

# Актуальная точка — 21.10.2026

Текущий main: `9d815e65d2fcdbc3bca34a273bc57bc8645dab88` (#359 merged). PR #360 открыт. Render deploy LIVE на main SHA; `/health` и `/ready` = 200. Основной `@ERA_1bot` работает через webhook; отдельный Commission `@MVKSRS_bot` через polling. Старое заключение о неверном BOT_TOKEN опровергнуто кодом и live logs; секрет не менять. После трёх исправлений review/кнопки адресные тесты 46 passed, 17 subtests; требуется полный CI точного финального SHA.

Для поддержки используется `PermissionGrant(permission=support.manage, scope_type=support_category, scope_id=1..5)`; для редакции литературы — `PermissionGrant(permission=literature.manage, scope_type=literature_category, scope_id=1)`. Категорийная литература даёт только очередь материалов и действия по материалам, не общие настройки расписания/модуля. Права проверяются заново на сервере для каждого callback и формы.

| Задача | Файлы / основные символы | Данные | Проверки |
|---|---|---|---|
| Регистрация и повторная подача | handlers/registration.py:registration_start,finish_registration; repositories/users.py:create_user_from_registration,resubmit_user_registration; handlers/emergency.py:start | users, social_profiles/social_links, consent, audit; FSM Redis | test_registration_admin_visibility, test_registration_card_async, test_native_admin_operations |
| Карточка заявки | services/admin_user_card.py:build_admin_user_card | User relations, photos, points | test_admin_user_card, test_registration_card_async |
| Аналитика, Excel, плановый отчёт | services/admin_analytics_service.py:build_analytics_payload; admin_dashboard_service.py; executive_excel_service.py; handlers/admin/analytics_filters.py; services/excel_service.py; handlers/admin/commands_ready.py | users, points, events/registrations, projects, tasks/submissions, activity metrics, lifecycle, offices, goals, audit | test_admin_analytics_service, test_admin_dashboard_service, test_executive_excel_service, test_analytics_filters |
| Определение активности | services/meaningful_activity_service.py; organization_health_service.py; organization_health_extended_service.py; era_efficiency_service.py | подтверждения, points, appointments; participation_lifecycles | соответствующие test_*activity*, test_*health*, test_*efficiency* |
| Сертификаты | services/certificate_service.py, certificate_pdf_service.py; handlers/certificates.py; api/v1/career.py | certificate_issues → portfolio_items; migration 0063 | test_certificates; postgres_certificate_season_race.py |
| Сезоны / ICS | services/ranking_season_service.py,event_calendar_service.py; handlers/ranking_seasons.py; api/v1/leaderboard.py,events.py | AppSetting ranking-season:; points; events | test_ranking_seasons,test_event_calendar; E2E readiness-exports |
| Выпуск | .github/workflows/ci.yml,tests.yml; Dockerfile; render.yaml; app/webapp.py | main → Render srv-d91r1j7avr4c73fs8h00, /ready | final SHA CI; migrations/races; deploy LIVE and logs |

Все пути app/ относительны корню app, кроме явно указанных tests/scripts/frontend/docs. Сервис использует общую ERA PostgreSQL dpg-d91r19vavr4c73fs837g-a; схему commission и другие сервисы не менять. Тестовые записи только в изолированных базах. Ключи, полные анкеты и дампы в документы/логи не помещать. Render SQL connector read-only; не пытаться обходить транзакционное ограничение. Автодеплой checksPass: второй ручной deploy после merge не запускать.

Аналитика 2.0: services/analytics_snapshot_service.py (build_analytics_snapshot, verified_activity_facts, roster_conditions), tests/test_analytics_snapshot.py. SQL aggregates; 7/30/90 дней; общий snapshot для native overview и basic Excel. Когортная воронка и health/efficiency подключены; финальный CI и выпуск отслеживать в состоянии.

Рост: services/analytics_growth_service.py:build_growth_snapshot; tests/test_analytics_growth.py. Native analytics_filters: analytics_growth, analytics_growth_gaps; admin API /analytics/growth; Excel «Рост 90 дней». Экспорт монтируется напрямую в analytics_filters, исторические management/survey routers не подключать целиком.

Scoped leaders: services/admin_analytics_service.py:build_scoped_leader_operations → leaders_access_service.scopes(tasks.manage); handlers/leaders_native.py:leader_operations; tests/test_scoped_leader_analytics.py. Все запросы задач/результатов/целей ограничены разрешёнными department/direction либо executive global. Обычный статус leader не расширяет scope.

Entity reports: analytics_snapshot_service.build_event_analytics/build_project_analytics/delivery_problem_counts → analytics_filters.analytics_entities/analytics_waiting; API /analytics/sections/{events|projects}; Excel «События 2.0»/«Проекты 2.0». tests/test_entity_analytics; PostgreSQL probe scripts/postgres_certificate_season_race.py. Сохранение native Excel routes проверяет test_system_audit_callback_regex.

Фото регистрации: handlers/registration.py:registration_photo_start/registration_photo/_show_registration_review/finish_registration → database/socials.SocialProfile; keyboards/registration.registration_review_keyboard; services/admin_user_card.send_admin_application_cards → notification_service.notify_admins_once(photo). Доставка через прежний safe_send_once/receipt, caption ≤900, full card отдельно. tests/test_registration_completion (quick upload, resubmit, preservation), test_registration_admin_visibility (photo caption).
Оформление регистрации: все REG prompts/resume — explicit HTML; referrals.registration_start_with_referral → общий registration._begin_registration. Legacy first_name при resume → full_name, код и прогресс сохраняются. tests/test_registration_completion: full flow/escape/referral OFF+ALL/legacy resume.

Точный остаток/пакеты PR: FINAL_RELEASE_BACKLOG_2026_10_20.md. Management report и общие verified facts/periods/report UI/attention actions уже включены в #359; не выполнять пакет повторно. Следующий gate — реальные Telegram/Excel сценарии и эксплуатационные зависимости.

Решение пользователя 20.10.2026: языковой пакет отложен, текущий язык интерфейса сохраняется. Локализация не блокирует текущую окончательную приёмку; выполнять только по отдельному запросу.

### Короткая управленческая сводка (пакет management-clarity)
- admin_analytics_service._management_period_facts/build_management_report → общий count_verified_users/count_new_members/held_events_between; management_report_text/details_text/attention/markup.
- commands_ready.management_report_action → период 1/7/30, overview/details/excel с единым snapshot. excel_report_service.management_summary_workbook → сохранён прежний лист + лист сравнения потоков.
- task_review_block2.task_attention_queue/action → Task/TaskSubmission, global tasks.manage, SQL pagination, optimistic card token + row lock; мутации leaders_workspace.change_task (общий аудит/напоминания).
- analytics_filters.analytics_waiting → needs_info/thread_waiting/answer errors + общий task_attention_condition и переходы к очередям.
- Проверки: tests/test_management_report.py, test_analytics_snapshot.py, test_entity_analytics.py, test_admin_analytics_filters.py, test_system_audit_callback_regex.py, test_leaders_native_workcenter.py.
