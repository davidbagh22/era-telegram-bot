## 2026-10-21 · Analytics 2.0 · рабочий этап (выше старых checkpoint)

Приоритет владельца: аналитика → полноценная регистрация и компактная карточка → остальная приёмка. Основное ТЗ: `docs/ANALYTICS_V2_SPEC.md`, main f41613f. Render подтверждён LIVE на f41613f (dep-dbce0m3m8hqs73bq4d20); это состояние до текущего PR.

В рабочей ветке: метаданные channel_post/message без текстов и авторов, dedup по chat/message, альбом=одна публикация, все темы/люди/анонимные администраторы, исключены боты/служебные/автопересылки канала. Учёт собственных успешных отправок также дедуплицируется. Проверка прав раз в 5 минут и вручную; неполный/устаревший период не становится нулём, нет вымышленной прошлой истории. Потеря прав/наблюдений прерывает непрерывное покрытие. Метрики Telegram и дневные ряды добавлены в общие PDF/Excel; журнал генерации виден только самому администратору.

UI: 6 компактных вкладок, 4 основных KPI, отдельные определения текущего состава и всех профилей, дневные графики Telegram и первых одобрений, раскрываемая методика, реальные переходы к заданиям/проектам/событиям/заявкам. 59 прежних метрик сохранены по группам; их фиксированные источниковые периоды явно отделены от выбранного диапазона основных KPI. Нулевые знаменатели → «Нет данных». Опросный пульс с выборкой/охватом отделён от условного операционного индекса. Новые API используют общий серверный доступ к админской аналитике; категорийный grant его не открывает.

PR #368 открыт. Повторный E2E: 46 passed, одно неверно ограниченное обращение к скрытой группе исправлено; реальный PDF за выбранные даты и responsive-проверки пройдены. Источники пишут в эксплуатационный лог только kind/status/coverage, без текстов/пользователей/секретов.

Первый полный локальный прогон: 1932 passed, 1 skipped, 105 subtests; 3 ошибки (старый UI-контракт, fresh SQLite create_all, список scheduler jobs) исправлены и перепроверены адресно. Review: сбои наблюдения немедленно инвалидируют покрытие в БД, pending-marker не снимается до успешного commit проверки прав; добавлены проверки другого worker и commit-граничного состояния.

Адресные проверки: 32 passed; сборка/TypeScript и ruff E9,F — passed. Полный прогон и CI ещё выполняются. PostgreSQL race probe добавлен в CI (30 одновременных доставок → 1 факт), миграция 0064 добавляет только таблицы наблюдений. Регистрации и реальные участия не менялись.

Не закрыто: полный CI/E2E, review, merge/автоматический deploy, реальные источники/права и скачивание отчёта в Telegram, визуальная проверка iPhone, наблюдение 24 часа. В этом окружении загрузка локального Chromium не удалась; E2E должен пройти в CI. Авторизованный Telegram Web ранее заблокирован automatic approval review; отдельного разрешения на конкретный сценарий не получено, обхода нет. Полная настройка всех 59 метрик под произвольные даты/исторические сравнения требует отдельных подтверждённых источников; текущие срезы не выдаются за исторические. Следующим отдельным этапом остаётся регистрация + карточка по скриншотам. Юридический draft #364 не утверждён, смена раскрытых паролей не подтверждена. Ни «10/10», ни полная готовность не заявлены.

## 2026-10-21 · Admin analytics / PDF release candidate

- Admin analytics: prominent PDF export, 30/90/180/365-day and custom report dates, accessible navigation, expand-all metrics, explicit empty risks and Excel fallback.
- PDF uses the existing executive workbook facts and all 13 sections, plus current organization/goal lists and separately permission-checked media aggregates; adds health metrics, priorities, cohort-safe vector bars, period caveats, page numbers and Unicode font. No separate business formulas or raw vector answers.
- Endpoint shares the existing dashboard-access dependency, validates format/dates, uses Yerevan report day and private/no-store responses; PDF layout runs outside the event loop.
- Local: frontend build/typecheck passed; executive PDF/Excel + privacy tests passed (12 tests, 5 subtests). PDF pages rendered and visually checked. Browser PDF export E2E added for CI.
- UI follow-up: long period labels no longer squeeze the heading; added admin export/heading overflow checks at 320/430/768 px.
- Review follow-up: preserve formula-looking titles as literal text in Excel/PDF (regression tests); short appendix sections flow continuously. Isolated seeded integration generated all 13 sections; no production writes.
- Pending: full CI/review, merge, automatic deployment, authenticated production download and release observation. These changes are not production evidence.

# Актуальный checkpoint защиты данных — 21.10.2026

Следующий этап по запросу владельца: `docs/RELEASE_ACCEPTANCE_TZ_2026_10_21.md` — критерии завершения вместо субъективной оценки7/10. Ветка `fix/telegram-miniapp-readiness-20261021` поверх #363 меняет framing Mini App на CSP с точным origin Telegram Web и возвращает430/768px в обязательный E2E. Адресные тесты заголовков/доступа/сессий:21passed,5subtests. До полногоCI/merge/auto deploy/реального открытия это не production. Юридический проект #364 отдельно остаётся draft; реквизиты организации и аудиторияРА получены от владельца, секреты и личные идентификаторы в проект не включены. Автоматическую смену раскрытых паролей и юридическую приёмку не заявлять.

Production подтверждён на `43209ba9` (#360–362 merged), Render `dep-dbc8p0dg1s2s738i29jg` LIVE; все пять main CI jobs success. PostgreSQL external allowlist=[]; post-ACL encrypted backup и изолированный restore подтверждены. Реальная Telegram-проверка /start, сводки/7д/деталей, очереди задач и Excel пройдена; полная multi-role/Mini App приёмка не завершена. E2E:43 passed/2 skipped (ширины430/768). Контроль24ч — не ранее22.10 13:59 Asia/Yerevan.

Новый запрос владельца: максимальная защита и юридическое оформление РА/РФ. Ветка `fix/privacy-access-hardening-20261021` закрывает community-доступ неодобренных аккаунтов и кеширование API; до CI/merge/deploy это НЕ production. Юридические факты, подтверждённые меры, источники и решения оператора: `docs/SECURITY_LEGAL_CHECKPOINT_2026_10_21.md`. Новое согласие не утверждалось/не публиковалось, старые consent записи и production-данные не менялись. Требуются точные реквизиты оператора, аудитория/гражданеРФ, решение по географии обработки, отдельные цели/согласия и сроки/представительство. Не заявлять полное юридическое соответствие.

Ниже сохранены исторические checkpoint: сверять их с актуальным SHA и этим разделом.

# Исторический checkpoint — 21.10.2026

## После #359
- GitHub `main` подтверждён на `9d815e65d2fcdbc3bca34a273bc57bc8645dab88`; #359 объединён, #360 открыт. Проверки #359 ранее прошли: 1903 passed, 1 skipped, 1 xfailed, 97 subtests; E2E, frontend/security и PostgreSQL проверки зелёные.
- Production подтверждён: Render deploy `dep-dbbv1oe7bikc73ahfhqg` LIVE на SHA `9d815e65d2fcdbc3bca34a273bc57bc8645dab88`; повторно `/health` и `/ready` = 200, после deploy error logs отсутствуют, одна рабочая instance. ВАЖНО: прежний вывод о неверном BOT_TOKEN был ошибочным. Основной `@ERA_1bot` (ID `8481922061`) работает через webhook; `@MVKSRS_bot` (ID `8842890484`) — отдельный Commission poller в том же сервисе. Startup log подтверждает основной bot username, webhook POST = 200 и реальные обновления ERA обработаны (последнее проверенное `21.10 08:29:55 UTC`). BOT_TOKEN не менять на основании Commission polling log. Меню указывает на правильный app target, обновление release URL Telegram пока не подтвердил.
- 24-часовой post-release контроль ещё не наступил: deploy LIVE `20.10 22:55:29 UTC`, контрольная отметка `21.10 22:55:29 UTC`.
- Категорийные права поддержки/редакции отправлены отдельным PR #360 из `feat/category-scoped-staff-access-20261021`; PR открыт. Существующие `PermissionGrant` получают `support_category` scopes по категориям обращений и отдельный `literature_category` scope. Повторная проверка нашла и исправила три дефекта: delivery workers повторно проверяют текущую категорию, callback назначения категории правильно разбирает ID, литературный индикатор сохраняется при изменении категории. Адресный набор после исправлений: 46 passed, 17 subtests. Полный CI финального SHA обязателен до merge. Предыдущий полный локальный checkpoint: 1905 passed, 1 skipped, 1 xfailed, 97 subtests. Проверены чужая категория, подмена ID, отзыв, назначение, список/вложения, delivery после переноса/частичного отзыва и запрет настроек всего модуля для литературы.

## Открытые зависимости/приёмка
- Render workspace `David's workspace` подтверждён. Основной webhook identity соответствует целевому боту; production secrets не менялись. Просмотр реальных исходящих экранов и полный цикл под отдельными ролями всё ещё не подтверждены одним лишь входящим webhook log.
- External PostgreSQL allowlist подтверждён как `0.0.0.0/0`. Render подтверждает текущий service и DB; DB connection activity идёт с private `10.x` адресов. По актуальным правилам Render allowlist ограничивает только public ingress, поэтому пустой allowlist оставит same-region private networking. MCP не умеет менять ACL; CLI/API credential недоступны. Нужен разрешённый Dashboard fallback/доступ администратора; перед изменением повторно проверить bot/migrations/backup.
- Последний encrypted GitHub backup — run `39552815304` от `21.10 06:00 UTC`, SHA `9d815e65`; snapshot, изолированный restore PG18, encryption/verification и artifact — success. S3 upload/restore skipped из-за отсутствия credentials.
- Не подтверждены редактор/календарь и 180-дневное покрытие литературного и игрового контента; согласование сертификатного шаблона/подписанта, правил сезонов и текстов обработки данных; реальные Telegram-сценарии и 24-часовой мониторинг.
- Не сбрасывать регистрацию повторно; не создавать фиктивные production-участия и массовые тестовые рассылки. Языковой пакет не добавлять.

Сведения ниже сохранены как исторический post-release checkpoint `#357/#358` и не являются описанием текущего main/prod.

# Состояние ЭРА — 20.10.2026, после выпуска #357

## Последний production — #358, оформление регистрации
- Main 4fc319ce1fff74e1ab12980f0343ef500366918d; PR #358 MERGED. Tested head 5f19bcbcae4ac742960df10ccbc4555516e4bd89, tree 3c06b550c13494504771b3f0c21c0b54b76dcae9; merge сохранил #357 ancestry и точное дерево.
- Все 6 PR checks и 5 main checks success; 1897 passed, 97 subtests, 1 skipped/1 xfailed. Main run 39406910833.
- Render dep-dbbk8bek1f9s73bumib0 LIVE 20.10 10:37:41 UTC / 14:37:41 Asia/Yerevan; штатный auto deploy. После LIVE реальный /health=200 commit=4fc319c, /ready=200 ready; error logs после начала deploy отсутствуют.
- Все доверенные REG prompts и resume отправляются с явным HTML; пользовательские ответы в review экранируются. Referral использует тот же _begin_registration и сохраняет код/существующую анкету; legacy first_name при resume переводится в рабочий full_name. Проверены полный маршрут и referral OFF/ALL. Старые сообщения Telegram не перерисовываются; /start → «Продолжить анкету» даёт новый экран без сброса данных.
- Реальное отображение новых сообщений в клиенте пользователя ещё не наблюдалось. Незавершённая анкета — штатное сохранение прогресса, не причина повторять reset.

## Предыдущий production — #357
- main: 13cdabde0500178da1a29c45dab4a66501b0338e. PR #357 MERGED; родители bcb0299 (#356) и d0fd9531; кодовое дерево 5b4a5449fd5b86a2d40d75c2fec5584ef2fc6e93 совпало с проверенным деревом PR.
- Render dep-dbbjbo0473hc73dkvusg LIVE 20.10 09:36:50 UTC / 13:36:50 Asia/Yerevan. Штатный checksPass auto deploy, без ручного дублирования.
- Реальный HTTP после LIVE: /health 200 commit=13cdabd; /ready 200 ready. /api/v1/admin/analytics/{overview,growth,sections/events} и /analytics/export.xlsx = 401 без авторизации. Startup complete; новых error logs не найдено. React /app/ обслуживается в production; native Telegram остаётся основным маршрутом.
- PR final head d0fd9531: оба workflows и все 6 jobs success. 1895 passed, 1 skipped, 1 xfailed, 97 subtests; линтер, зависимости/секреты, frontend, E2E, реальные PostgreSQL migrations/races/builders и Redis FSM прошли. Main run 39400088885: все 5 jobs success.

## Выпущено
- Сброс предоставленного пользователем точного Telegram ID завершён ещё в #356. Receipt complete, шифрованная резервная копия есть, private FSM очищен. Старый user_id=31 архивирован с синтетическим ID; community identity отвязана, ledger/audit/FKs сохранены. На новом старте #357 операция вернула already_complete: новая регистрация повторно не сбрасывается. Ключ находится только в Render env; не выводить и не регенерировать.
- Фото: quick/full анкета позволяет необязательно добавить/заменить фото перед подтверждением; preview и resume; motivation больше не обнуляет photo_file_id. Submit/resubmit сохраняет SocialProfile. Администраторы получают фото+короткую подпись через прежний durable receipt; учитываются emoji/UTF-16 и лимит caption. Полная анкета открывается нативной кнопкой. Недоступное фото не скрывает текст. Проверены fresh-session DB/card, повторная подача и доставка с caption.
- Аналитика: общий verified SQL snapshot 7/30/90, первое audit approval, retention одним SQL statement; NULL вместо выдуманных процентов. Рост 90 дней по реально наблюдаемым датам/аудиту, два distinct результата, роли не заменяют историю. Native Telegram/API/Excel, dashboard/health/efficiency согласованы. Лимиты 500/200 сняты; проверены 501/501/201.
- Scoped результаты лидеров по свежим tasks.manage grants/offices: свои задачи/нагрузка/результаты/цели. Роль leader не выдаёт глобальные права. Реальный change_role пишет именно тот audit, который читает рост.
- Events: регистрации, реальная явка, новые/вернувшиеся посетители и реальные отзывы разделены. Projects: статусы отдельно от подтверждённых вкладов/этапов, просрочки и отсутствие результата. Active projects = approved/in_progress во всех общих сводках. Открытые task-scoped blockers входят в distinct attention; закрытые задачи не включаются. Delivery warnings по существующим receipts без повторных отправок.
- Все review threads #357 resolved. Перед выпуском других открытых PR не было; старые заменённые ветки не объединять повторно.

## Что ещё НЕ завершено
0. Подтверждён остаток именно админ-аналитики: присланная сводка использует ledger-only meaningful_user_ids_since, ручные отчёты без previous, daily comparison только users_total, literature active — накопительно, не все attention queues/actions согласованы. Следующий приоритет — пакет A из FINAL_RELEASE_BACKLOG_2026_10_20.md; затем B и реальные сценарии. GitHub open PRs = 0 на проверке. Не заявлять, что старый ежедневный отчёт уже полностью унифицирован новым overview.
1. PostgreSQL external allowlist всё ещё 0.0.0.0/0. Render MCP не предоставляет update ACL. Browser login не завершён, прежняя вкладка отсутствует; API-ключа/CLI в среде нет. Нужен действующий безопасный вход Render, затем internal-only и проверка bot/migrations/backup. Не заявлять, что сеть уже закрыта.
2. Дополнительная S3-копия без credentials провайдера не подключена. Независимый от Render encrypted GitHub backup УЖЕ работает: run 39377805234 success 20.10 06:00 UTC; download OIDC snapshot, isolated PG18 restore, encrypt/verify/upload artifact — success. S3 upload/download/restore skipped. Не путать отсутствие S3 с отсутствием резервной копии.
3. Языковой пакет отложен пользователем 20.10.2026 и исключён из текущей обязательной приёмки; текущий язык интерфейса сохраняется. Категорийное делегирование поддержки/редакции остаётся обязательным. Существующие global grants и scoped projects/tasks сохранены, admin root не расширять.
4. Реальная клиентская Telegram-приёмка: повторная анкета с фото самим пользователем, цикл задач с разными участниками, canary рассылки/игр/мероприятий. Не создавать фиктивных участников и массовые production-рассылки как тест. HTTP/CI не заменяют эти факты. 24 часа после выпуска ещё не прошли.

## Как продолжать экономно
Этот post-release checkpoint сохранён в ветке fix/registration-html-20261020, поверх main 4fc319ce. В main документы могут описывать предвыпускной этап; сначала сверить фактические main/prod SHA и этот checkpoint, не повторять уже завершённый аудит/сброс/релиз. Карта: AI_WORK_MAP.md; формулы: AI_ANALYTICS_SPEC.md; полный остаток: ERA_FINAL_TZ_2026_10_19.md.

Тесты: BOT_TOKEN=0000000000:LOCALTEST ../era-test-env/bin/python -m pytest -q <точные тесты>. Изменения через отдельную ветку и PR. Не трогать commission-бот, его схему и чужой untracked файл app/.commission_bot_community.py.vo6FgJ. Не печатать secrets/анкеты/дампы. Не запускать ручной deploy при активном auto deploy.

## В работе — management-clarity-20261020
- Админ-сводка переведена на bounded verified facts и первое audit-одобрение, сравнение потоков с равным SQL-периодом; текущий состав/проекты не получают выдуманную историческую динамику.
- Короткий обзор: решения → участники → результаты; полные показатели/диагностика по кнопке. 1/7/30 сохраняются в деталях, обновлении и Excel; Excel использует тот же metrics/comparison.
- Все предупреждения видимы, без attention[:3]. Литература явно разделяет текущих подписчиков и накопительные отметки. Полные локальные дни мероприятий названы явно.
- Добавлена нативная пагинированная очередь проблемных задач: существующий общий change_task, свежие global tasks.manage права, row lock, версия карточки, подтверждение отмены. Перенос overdue восстанавливает review при ожидающем результате, иначе in_progress; ledger не меняется.
- Пока НЕ production: ожидаются адресные тесты, полный CI, review, merge и штатный Render deploy. Категорийное делегирование — следующий пакет.
