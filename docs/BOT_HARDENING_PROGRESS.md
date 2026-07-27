# BOT HARDENING PROGRESS

## Текущий статус

Оценка готовности: 7/10.

Этап 1: база данных и транзакции — завершён и смержен в `main`.

Этап 2: система баллов — завершён и смержен в `main`.

Ретроспективная очистка этапов 1-2 — завершена и смержена в `main`.

Этап 3: роли и права — завершён и смержен в `main`.

Этап 4: QR-система — не реализована.

Доработка личного кабинета задач — завершена и смержена в `main`.

Этап 5: мероприятия — завершён и смержен в `main`.

Этап 6: задачи, проекты, опросы, портфолио — в работе.

## Завершённые этапы

### Этап 1. База данных и транзакции

Выполнено:
- добавлена idempotency metadata для операций баллов: `source_type`, `source_id`, `idempotency_key`;
- добавлена уникальность `points.idempotency_key`;
- повторный idempotency key возвращает существующую операцию и не создаёт дубль;
- списание баллов блокирует пользователя и запрещает отрицательный баланс;
- регистрация на мероприятие блокирует строку мероприятия перед проверкой лимита мест;
- начисление баллов за посещение, списание за аукцион и обмен награды получили стабильные idempotency keys;
- старые миграции с динамическим `0001_initial` защищены от повторного создания уже существующих таблиц/колонок;
- добавлена миграция `0009_points_idempotency`;
- добавлена merge-миграция `0010_merge_surveys_and_points_heads`, чтобы `head` снова был однозначным;
- добавлены тесты `tests/test_points_transactions.py`.

Проверка:
- `python -m pytest` — 131 passed;
- `python -m alembic upgrade heads` на локальной SQLite async базе — успешно;
- `python -m alembic upgrade head` на локальной SQLite async базе — успешно.

PR: #66.

Merge commit: `e6ed094e6b0fe41925e4fe9d118042c1d7a24491`.

CI:
- Tests: success on `dfbc039070a8bc9630f2bc7930415cef6be7400b`;
- Bot checks: success on `dfbc039070a8bc9630f2bc7930415cef6be7400b`.

### Этап 2. Система баллов

Выполнено:
- все production-вызовы `add_points(...)` получили `idempotency_key`;
- прямое создание `PointTransaction` вне `points_service` запрещено тестом;
- перевод баллов между участниками переведён на `add_points(...)` с FSM `transfer_id`;
- ручные начисления используют ключ с Telegram `message_id`, поэтому повтор update не дублирует операцию, а новая ручная операция не блокируется;
- сущностные операции используют стабильные ключи: registration, event attendance, event activity, task submission, project approval, auction win, reward redemption, partner offer, badge award, proposal points;
- добавлен `make_idempotency_key(...)` для компактных стабильных ключей;
- добавлен аудит-тест `tests/test_points_idempotency_audit.py`.

Проверка:
- `python -m pytest` — 133 passed.

PR: #68.

Merge commit: `c07e00090e718bc480664d76c5cf0187d70bc7e1`.

CI:
- Tests: success on `fbff6397febe8633a9c2923ce333b8e7c814a7e3`;
- Bot checks: success on `fbff6397febe8633a9c2923ce333b8e7c814a7e3`.

### Ретроспективная очистка этапов 1-2

Проверено:
- подключение router через `app/bot.py`, `app/handlers/admin/__init__.py`, `app/handlers/participant/__init__.py`;
- production-вызовы `add_points(...)`, прямые создания `PointTransaction`, операции регистрации на мероприятия, подтверждения участия, наград, аукционов и партнёрских предложений;
- старые callback handlers, которые дублировали активные маршруты баллов и регистрации, но не были подключены к bot dispatcher.

Удалено:
- неподключённые заменённые handlers: `registration_addons.py`, `admin/activity_files.py`, `admin/dashboard_quick.py`, `admin/event_flow.py`, `admin/project_full_review.py`, `admin/project_team_review.py`, `admin/proj2.py`, `admin/task_guard2.py`, `admin/task_review.py`, `admin/task_review_clean.py`, `admin/user_reward_direct.py`.

Архитектурное решение:
- рабочими путями для операций баллов остаются активные router-модули, подключённые в `admin/__init__.py` и `participant/__init__.py`;
- прямое создание `PointTransaction` вне `points_service` по-прежнему запрещено аудит-тестом;
- добавлен системный тест, который не даёт вернуть удалённые дублирующие handlers.

Проверка:
- `python -m pytest tests/test_system_wide_audit.py tests/test_points_idempotency_audit.py tests/test_points_transactions.py tests/test_event_registration_block14.py tests/test_event_activities_block15.py tests/test_reward_redemptions.py tests/test_auction_block17.py` — 29 passed;
- `python -m pytest` — 134 passed.

PR: #70.

Merge commit: `b3ef0ff846051d39aed40a52a47f485b44fe3f65`.

CI:
- Tests: success on `66cada93b782840481c6a6f0a5d0b169dbb750cb`;
- Bot checks: success on `66cada93b782840481c6a6f0a5d0b169dbb750cb`.

## Открытые проблемы

- QR-система отсутствует в коде: нет генерации, подписи, срока действия, привязки к мероприятию/пользователю, scan/check-in handler и одноразового использования.
- Production backup нельзя считать подтверждённым без `BACKUP_DATABASE_URL` и реального artifact restore.
- Production Render / Telegram smoke test не проверялись.

### Этап 3. Роли и права

Проверено:
- фактические источники прав: `users.role`, `settings.admin_ids`, `permission_grants`, `is_blocked`, `is_archived`, `application_status`;
- активный модуль управления ролями и правами `app/handlers/admin/rights_block6.py`;
- прямые callback-сценарии смены роли, блокировки, архивации и переключения technical permissions.

Найдено:
- проверки прав были размазаны по handler helpers;
- не было единого серверного правила для самопонижения/самоповышения, изменения собственных technical permissions и защиты последнего администратора.

Сделано:
- добавлен `app/services/authorization_service.py` как единый слой решений для критических операций с ролями, доступом и technical permissions;
- `rights_block6.py` переведён на этот сервис для опасных действий;
- добавлены негативные тесты на прямой callback-обход: собственная роль, собственные права, последний администратор, основной администратор, мгновенная потеря delegated permissions после блокировки;
- добавлена фактическая матрица прав `docs/ROLE_PERMISSION_MATRIX.md`.

Проверка:
- `python -m pytest tests/test_authorization_service.py tests/test_system_wide_audit.py tests/test_v2_scenarios.py tests/test_full_bot_flow.py` — 30 passed.
- `python -m pytest` — 140 passed.
- `git diff --check` — успешно.

PR: #72.

Merge commit: `3cc0cd211e53735bfcda304c80fd0633bff85555`.

CI:
- Tests: success on `d540c27a6e844b6b2c345cccefe5e32e794dcf67`;
- Bot checks: success on `d540c27a6e844b6b2c345cccefe5e32e794dcf67`.

### Этап 4. QR-система

Проверено:
- поиск по handlers, services, models, migrations, tests и docs по маркерам `qr`, `qr_code`, `qrcode`, `checkin`, `scan`, `attendance`, `proof`, `signature`;
- существующие флоу посещения: ручная отметка администратором, reminder callback `attendance:*`, selfie proof.

Найдено:
- QR-система — не реализована;
- существующие attendance/selfie флоу не являются QR: у них нет подписанного токена, срока действия QR, одноразового scan/check-in, привязки QR к пользователю и мероприятию;
- реализовывать QR с нуля в рамках аудита нельзя без продуктового решения по UX сканирования и формату допуска.

Сделано:
- добавлен аудит-тест `tests/test_qr_system_audit.py`, который фиксирует отсутствие QR-флоу и не позволяет ошибочно считать его подтверждённым.

Проверка:
- `python -m pytest tests/test_qr_system_audit.py tests/test_event_registration_block14.py tests/test_full_bot_flow.py` — 10 passed;
- `python -m pytest` — 141 passed;
- `git diff --check` — успешно.

PR: #75.

Merge commit: `9d96c50e066fe0462324ea4464b8da836c4ffe62`.

CI:
- Tests: success on `67cf2378abc0c691b3588f43844908d45f341fc6`;
- Bot checks: success on `67cf2378abc0c691b3588f43844908d45f341fc6`.

### Доработка личного кабинета задач

Сделано:
- в `Личный кабинет → Задачи` добавлен отдельный раздел `🌐 Общие задачи`;
- активные задачи теперь показывают только личные/взятые задачи;
- общие задачи показывают опубликованные `challenge`-задачи, куда участник ещё не вступил;
- архив не смешивается с открытым набором.

Проверка:
- `python -m pytest tests/test_participant_tasks_cabinet.py tests/test_v2_scenarios.py tests/test_system_wide_audit.py tests/test_full_bot_flow.py` — 26 passed;
- `python -m pytest` — 143 passed;
- `git diff --check` — успешно.

PR: #77.

Merge commit: `befa64910a42f8c322945afbb44e632bb7ced568`.

CI:
- Tests: success on `55462d8f3bf21486b42476beb4d622a3735e5260`;
- Bot checks: success on `55462d8f3bf21486b42476beb4d622a3735e5260`.

### Этап 5. Мероприятия

Проверено:
- активные participant event handlers: афиша, карточка, регистрация, лимиты мест;
- сервис регистрации `event_service.register_for_event`;
- admin status callbacks для открытия регистрации, закрытия, старта и завершения;
- подтверждение посещения и начисление баллов за attendance.

Найдено:
- смена статуса мероприятия принимала целевой статус из callback без матрицы допустимых переходов;
- старая или подменённая кнопка могла попытаться перескочить жизненный цикл мероприятия.

Сделано:
- добавлена матрица `EVENT_STATUS_TRANSITIONS`;
- admin callback смены статуса теперь проверяет переход по текущему состоянию мероприятия;
- добавлены негативные тесты на прямые callback-прыжки между статусами.

Проверка:
- `python -m pytest tests/test_event_status_transitions.py tests/test_event_registration_block14.py tests/test_stability_bindchat_projects.py tests/test_stabilization_contracts.py tests/test_system_wide_audit.py` — 27 passed;
- `python -m pytest` — 145 passed;
- `git diff --check` — успешно.

PR: #77.

Merge commit: `befa64910a42f8c322945afbb44e632bb7ced568`.

CI:
- Tests: success on `55462d8f3bf21486b42476beb4d622a3735e5260`;
- Bot checks: success on `55462d8f3bf21486b42476beb4d622a3735e5260`.

## Следующий этап

Этап 6. Задачи, проекты, опросы, портфолио:
- проверить пользовательские и админские маршруты задач, проектов, опросов и портфолио;
- убрать дубли обработчиков, если они пересекаются с активными сценариями;
- усилить прямые callback-переходы серверными проверками доступа.

### Этап 6. Задачи, проекты, опросы, портфолио

Проверено:
- активные participant task handlers и порядок подключения router в `app/handlers/participant/__init__.py`;
- сценарии `cabinet:tasks`, `tasks:list:*`, `task:view:*`, `task:join:*`, `task:result:*`;
- старые task addon handlers, которые дублировали карточку задачи, список задач и отправку результата.

Найдено:
- пользовательские задачи имели несколько источников правды: основной `task_block2.py` и старый подключённый `task_flow.py`;
- старый подключённый handler мог показывать задачи без нового раздела `Общие задачи`;
- прямой `task:view:*` для опубликованной общей задачи не проверял role-фильтр аудитории.

Сделано:
- вступление в общую задачу перенесено в основной `task_block2.py`;
- просмотр и вступление в общую задачу теперь проверяют аудиторию задачи;
- старые duplicate task handlers удалены и закреплены системным аудит-тестом.

Проверка:
- `python -m pytest tests/test_participant_tasks_cabinet.py tests/test_system_wide_audit.py` — 14 passed;
- `python -m pytest` — 147 passed;
- `git diff --check` — успешно.

PR: pending.

Merge commit: pending.

CI:
- Tests: pending;
- Bot checks: pending.
