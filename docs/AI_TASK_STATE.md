# Состояние ЭРА — 20.10.2026

## Production / сброс — выполнено
- PR #356 MERGED, main/prod bcb029947459380a8e690cf06711f7f817b5f974. Render LIVE dep-dbbb03bm8hqs738ocb80, 20.10 00:05 UTC. /health и /ready = 200, health commit bcb0299.
- Точный целевой Telegram ID предоставлен пользователем. Reset receipt = complete, encrypted_snapshot присутствует. Старый user_id=31 архивирован с синтетическим Telegram ID, community identity user_id=NULL. Активной users-записи с исходным ID пока нет: доступна новая регистрация через /start. Прежний ledger сохранён: 2 записи / 105 баллов. Связей leader_chat_memberships нет. Ключ резервной копии остаётся только в Render env, не публиковать и не регенерировать.
- Полная реальная повторная отправка анкеты самим пользователем ещё не наблюдалась; не объявлять её проверенной через Telegram-клиент.

## Аналитика — PR #357, выпуск ожидается
- Remote head перед текущим исправлением: 28044773159ac426d6779e0dd9b7fd05035af6a3. Local branch feat/entity-analytics-20261020, code parent b4ee3b75. Проверять фактический HEAD и remote SHA перед продолжением.
- На предыдущем head frontend/E2E/PG/secrets прошли; backend 1888 passed, 1 failed: static callback audit не распознавал .register для Excel. Заменено стандартными decorated wrappers, общий защищённый exporter сохранён, legacy routers не монтируются целиком. Адресный audit пройден.
- Реализованы общий verified SQL snapshot 7/30/90, first audit approval, cohort retention (один SQL snapshot числителя/знаменателя), NULL при отсутствии базы, digital/office отдельно. Подключены native Telegram, API, Excel, dashboard, health, efficiency и executive export. Лимиты 500/200 удалены, проверены 501 events/projects и 201 goals.
- Рост 90 дней: фактические approval/role audits, два разных event/task/project, дедуп attendance+points, сроки и пагинация разрывов; роль не заменяет историю. Незавершённый этап не называется уходом.
- Лидеры: scoped task results/workload/month goals по свежим tasks.manage grants/offices. Обычный leader не получает общий доступ, отзыв grant проверен. Native private-only «Результаты команды».
- Новые срезы events/projects: реальные посещения отдельно от регистраций и баллов; waitlist/отмены вне знаменателя; первый/вернувшийся посетитель; реальные отзывы и coverage. Статусы проектов отдельно от dated contributions/completed milestones, overdue и отсутствие подтверждённых результатов весь период. Telegram/API/Excel — общие формулы. Доставка отчётов/рассылок — по существующим receipts, без новых уведомлений/повторных отправок.
- Health/efficiency выровнены по held events, attendance, feedback и in_progress; историческая конверсия отделена от текущих ролей. Nullable feedback согласован с API/frontend.
- Последняя адресная проверка: 35 passed + 17 subtests; lint passed; frontend build passed. PostgreSQL CI probe дополнен реальным выполнением всех analytics builders на migrated isolated DB. Требуется полный CI финального нового SHA, review → merge → штатный auto deploy main → /ready/logs.

## Следующие действия
1. Commit текущих только ERA analytics файлов и docs, push в #357 с expected remote SHA; дерево remote должно совпасть с local.
2. Дождаться final-head CI, исправить реальные ошибки; merge #357 при успешных checks. Render autoDeploy checksPass: не запускать второй ручной deploy; main CI тоже задерживает выпуск.
3. Проверить prod SHA, /ready, ошибки, доступность native routes без тестовых записей/рассылок в production.
4. Проверить security/backup: PostgreSQL ipAllowList 0.0.0.0/0 ещё не изменён (Render MCP не даёт update ACL). Текущий database-backup workflow использует OIDC HTTPS snapshot, а не внешнее прямое PG-подключение; проверить фактические источники перед политикой internal-only. S3 extra copy требует настройки провайдера; GitHub encrypted artifact backup — существующий отдельный слой.

## Остаток итогового ТЗ
Полная AM/EN локализация/редакторская приёмка; категорийное делегирование поддержки/редакции; независимый backup provider/ACL по факту доступов; реальные Telegram-клиентские сценарии и 24 часа наблюдения. Полный контракт: docs/ERA_FINAL_TZ_2026_10_19.md. Не выдавать CI за реальную приёмку.

Тесты запускать с BOT_TOKEN=0000000000:LOCALTEST в ../era-test-env. Комиссионный бот, его схему и чужие изменения не трогать. Начинать с этого файла и AI_WORK_MAP; не перечитывать весь проект.
