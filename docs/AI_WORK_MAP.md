# Карта точечной работы ЭРА

База production: 982c3ebf. Продолжение PR #356: remote head da1259ea, local d68f4b12, одинаковое дерево 2f1a8a7b. При смене SHA сверять только изменённые модули.

| Задача | Файлы / основные символы | Данные | Проверки |
|---|---|---|---|
| Регистрация и повторная подача | handlers/registration.py:registration_start,finish_registration; repositories/users.py:create_user_from_registration,resubmit_user_registration; handlers/emergency.py:start | users, social_profiles/social_links, consent, audit; FSM Redis | test_registration_admin_visibility, test_registration_card_async, test_native_admin_operations |
| Карточка заявки | services/admin_user_card.py:build_admin_user_card | User relations, photos, points | test_admin_user_card, test_registration_card_async |
| Аналитика, Excel, плановый отчёт | services/admin_analytics_service.py:build_analytics_payload; admin_dashboard_service.py; executive_excel_service.py; handlers/admin/analytics_filters.py; analytics/service.py; handlers/admin/analytics.py | users, points, events/registrations, projects, tasks/submissions, activity metrics, lifecycle, offices, goals, audit | test_admin_analytics_service, test_admin_dashboard_service, test_executive_excel_service, test_analytics_filters |
| Определение активности | services/meaningful_activity_service.py; organization_health_service.py; organization_health_extended_service.py; era_efficiency_service.py | подтверждения, points, appointments; participation_lifecycles | соответствующие test_*activity*, test_*health*, test_*efficiency* |
| Сертификаты | services/certificate_service.py, certificate_pdf_service.py; handlers/certificates.py; api/v1/career.py | certificate_issues → portfolio_items; migration 0063 | test_certificates; postgres_certificate_season_race.py |
| Сезоны / ICS | services/ranking_season_service.py,event_calendar_service.py; handlers/ranking_seasons.py; api/v1/leaderboard.py,events.py | AppSetting ranking-season:; points; events | test_ranking_seasons,test_event_calendar; E2E readiness-exports |
| Выпуск | .github/workflows/ci.yml,tests.yml; Dockerfile; render.yaml; app/webapp.py | main → Render srv-d91r1j7avr4c73fs8h00, /ready | final SHA CI; migrations/races; deploy LIVE and logs |

Все пути app/ относительны корню app, кроме явно указанных tests/scripts/frontend/docs. Сервис использует общую ERA PostgreSQL dpg-d91r19vavr4c73fs837g-a; схему commission и другие сервисы не менять. Тестовые записи только в изолированных базах. Ключи, полные анкеты и дампы в документы/логи не помещать. Render SQL connector read-only; не пытаться обходить транзакционное ограничение. Автодеплой checksPass: второй ручной deploy после merge не запускать.
