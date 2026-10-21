# Текущий checkpoint — 21.10.2026

## После #359
- GitHub `main` подтверждён на `9d815e65d2fcdbc3bca34a273bc57bc8645dab88`; открытых PR на последней проверке нет. #359 объединён. Его проверки ранее прошли: 1903 passed, 1 skipped, 1 xfailed, 97 subtests; E2E, frontend/security и PostgreSQL проверки зелёные.
- Production подтверждён: Render deploy `dep-dbbv1oe7bikc73ahfhqg` LIVE на SHA `9d815e65d2fcdbc3bca34a273bc57bc8645dab88`; `/health` и `/ready` = 200, после deploy error logs отсутствуют, одна рабочая instance. Но dispatcher стартовал как `@MVKSRS_bot` (ID `8842890484`), а ожидаемый бот — `@ERA_1bot`: проверить/исправить Render `BOT_TOKEN` и повторно подтвердить имя, не раскрывая/не копируя секрет в лог/репозиторий. До этого production-бот не принят.
- 24-часовой post-release контроль ещё не наступил: deploy LIVE `20.10 22:55:29 UTC`, контрольная отметка `21.10 22:55:29 UTC`.
- Категорийные права поддержки/редакции отправлены отдельным PR #360 (`4631a4324db009b09c4fb15b27eaa08cd20d8cef`) из `feat/category-scoped-staff-access-20261021`; PR открыт, `Bot checks` и `Tests` выполняются. Существующие `PermissionGrant` получают `support_category` scopes по категориям обращений и отдельный `literature_category` scope. Полный pytest до последних двух UI-regression тестов: 1905 passed, 1 skipped, 1 xfailed, 97 subtests; финальный адресный набор: 44 passed, 14 subtests. General-chat validator passed, system audit 9/9, Ruff, compile/diff clean. Проверены чужая категория, подмена ID, отзыв, назначение, список/вложения и запрет настроек всего модуля для литературы.

## Открытые зависимости/приёмка
- Render workspace `David's workspace` подтверждён. Deploy/health проверены выше; production polling identity не совпадает с целевой. BOT_TOKEN не менялся: у агента нет безопасного секрета для установки, и production secrets не меняются без явного разрешения.
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
