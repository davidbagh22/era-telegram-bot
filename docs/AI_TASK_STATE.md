# Состояние работы ЭРА

Обновлено 20.10.2026, Asia/Yerevan. Цель: сброс целевого аккаунта → завершение #356 → единая аналитика 2.0 → остаток итогового ТЗ → production-проверка.

## Проверено
- Prod LIVE/main 982c3ebf; PR #356 открыт, remote head 0705c380 (local d7fc3ba3, дерево 62b84e28 совпадает).
- Первый CI: PostgreSQL migrations/races, frontend и secrets прошли. Backend упал на прямых answer_document в новых handlers и старом assertion имени router. E2E seed передавал несуществующие actor_id/source в complete_onboarding. Исправления безопасной media-доставки и E2E seed прошли адресные проверки. Дополнительно закрываются review: ACTIVE event ICS, bootstrap admin queue, certificate export/anonymization с сохранением FK; 17 privacy/certificate tests passed. Требуется полный CI нового SHA.
- Точный поиск целевого аккаунта по заявленным username/телефону в users и username в leader_chat_memberships дал 0 строк. Сброс НЕ выполнен. Пользователь предоставил точный Telegram ID; найден archived participant, user_id=31. Есть 2 points, нет assigned tasks/projects/attendance/offices. Подготовлен replay-safe reset через ERA_REGISTRATION_RESET: encrypted User/FSM snapshot, архивная запись и ledger сохраняются, identity map отвязывается, очищается только private FSM. Адресный reset test пройден, защищённая команда и отдельный backup key сохранены в Render env; deploy старого main от конфигурации LIVE dep-dbbaa4rbc2fs73aepa4g не содержит reset hook. Требуется выпуск/выполнение и подтверждение read-only SQL. Нельзя считать reset выполненным заранее.
- ERA PostgreSQL ipAllowList содержит 0.0.0.0/0. Ограничение НЕ изменено: сначала сохранить внешнее подключение backup workflow; имеющиеся Render tools не предоставляют изменение ACL.

## Текущие действия
1. Зафиксировать исправления #356 и служебные документы, адресные тесты; новый PR CI → merge → auto deploy → /ready, schema, logs.
2. После получения ID определить users/dependencies; защищённая резервная копия затронутого профиля, транзакционный reset регистрации с сохранением ledger/audit и чужих данных, FSM только этого пользователя; реальная повторная подача. Не использовать commission reset.
3. Найти и устранить лимиты 500 событий/проектов, 200 целей в итогах admin_analytics_service. Утвердить формулы AI_ANALYTICS_SPEC, разделить digital / verified / responsibility; внедрить общий snapshot для Telegram/Excel, 7/30/90 дней и scoped доступ.
4. Полный остаток: docs/ERA_FINAL_TZ_2026_10_19.md, docs/READINESS_RELEASE_2026_10_19.md. AM/EN, категорийное делегирование, независимый backup, редакционная и реальная Telegram-приёмка пока НЕ завершены.

## Продолжение
Сначала git status и текущие remote main/PR SHA, затем AI_WORK_MAP. Адресные тесты запускать с BOT_TOKEN=0000000000:LOCALTEST (фиктивный token). Полный CI перед merge. Native media только через safe_answer_document; в E2E seed complete_onboarding(session,user) без лишних аргументов. Не повторять полный аудит. После этапа обновлять этот файл фактическим результатом.

20.10 03:30 AMT: CI head 0705c380 PostgreSQL/frontend/secrets success; E2E 42 passed/2 skipped/1 failure — calendar button overlapped by fixed registration footer. Increased event-detail bottom safe padding, preserving an actual clickable E2E test (no force click). Backend CI still running; after patch needs final-head CI. Reset env saved; actual reset NOT yet run. Local analytics branch checkpoints 2a717f47, 7fb639dd (not deployed).
## Следующий пакет аналитики (локальная ветка feat/analytics2-work-20261020)
Общий SQL snapshot текущей базы, первых одобрений по audit, distinct verified пользователей (включая подтверждения без баллов), удержания прошлой активной когорты, завершённых событий, текущих проектов и distinct задач на проверке/просрочке. Исторические снимки состава и воронка помечены недоступными; не выдуманы. Native обзор и Excel используют этот сервис. Лимиты 500/200 удалены. После #356 нужен отдельный PR/полный CI, не считать в production. Пульт/health/efficiency теперь используют общие verified facts; lifecycle правило «активен ИЛИ действующая должность» сохранено только для lifecycle, не KPI. Скоуп руководителей, когортная воронка и warnings остаются.

Аналитика: 32 адресных теста пройдены, lint/build пройдены; дополнительная проверка снятия лимитов 501 events/501 projects/201 goals пройдена. Executive Excel activity также переведена на verified facts выбранного периода. Nullable retention согласован с API и frontend типом. Release #356 final head ba763a16, CI 39341931367/39341931363, ожидается.
