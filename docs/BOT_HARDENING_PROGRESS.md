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

Этап 6: задачи, проекты, опросы, портфолио — завершён и смержен в `main`.

Дополнительный продуктовый блок: заявка участника и единая admin user card — завершён и смержен в `main`.

Дополнительный продуктовый блок: доступ в чаты после регистрации и approval — завершён и смержен в `main`.

Этап 7: рассылки и уведомления — в работе.

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

PR: #79.

Merge commit: `a2e1569d1253bad0ec9e21310c6169b9658e6741`.

CI:
- Tests: success on `6eca24f74ac9074b589d41bf1effffc1dd119849`;
- Bot checks: success on `6eca24f74ac9074b589d41bf1effffc1dd119849`.

#### Блок проектов: создание мероприятия из проекта

Проверено:
- активный поток `project:event:*` и порядок подключения router в `app/handlers/participant/__init__.py`;
- сценарий создания мероприятия из одобренного проекта через `project_event_photo_flow.py`;
- старые project add-ons, которые дублировали список проектов, удаление, отправку, поиск команды и создание мероприятия.

Найдено:
- несколько обработчиков могли владеть одним callback `project:event:*`;
- старые неподключённые add-ons сохраняли устаревшую логику проекта рядом с актуальным кодом;
- актуальный поток с афишей брал дату/время из `form_data` раньше структурных полей проекта.

Сделано:
- единственным владельцем `project:event:*` оставлен `project_event_photo_flow.py`;
- дата и время мероприятия теперь берутся из структурных полей проекта раньше старых `form_data`;
- проверка уже созданного мероприятия учитывает и `events.project_id`, и старый marker `[ERA_PROJECT_ID:*]`;
- старые duplicate project handlers удалены и закреплены системным аудит-тестом.

Проверка:
- `python -m pytest tests/test_project_to_event_flow.py tests/test_event_photo_contracts.py tests/test_stability_bindchat_projects.py tests/test_full_bot_flow.py tests/test_system_wide_audit.py` — 28 passed;
- `python -m pytest` — 149 passed;
- `git diff --check` — успешно.

PR: #80.

Merge commit: `412124862c373dc2090cf1c93caa761fc707131f`.

CI:
- Tests: success on `5b93b4b4e0a3583f2b45f8503b1175041349b9dd`;
- Bot checks: success on `5b93b4b4e0a3583f2b45f8503b1175041349b9dd`.

#### Блок опросов

Проверено:
- пользовательский вход в опрос `survey:start:*`;
- сохранение ответа после старта FSM;
- админские статусы опросов `draft`, `active`, `sent`, `archived`.

Найдено:
- участник мог открыть черновик опроса прямым callback `survey:start:*`;
- если опрос архивировали после старта, FSM всё равно мог сохранить финальный ответ.

Сделано:
- участникам доступны только статусы `active` и `sent`;
- перед сохранением ответа статус опроса проверяется повторно;
- добавлен контракт-тест, который закрывает доступ к `draft` и `archived`.

Проверка:
- `python -m pytest tests/test_admin_surveys.py tests/test_admin_analytics_filters.py tests/test_system_wide_audit.py` — 22 passed;
- `python -m pytest` — 150 passed;
- `git diff --check` — успешно.

PR: #81.

Merge commit: `4614f1618cac5d98619889d354fb29c9aa21e3d1`.

CI:
- Tests: success on `d940c07389c212af4c7e586a44cca13664703e03`;
- Bot checks: success on `d940c07389c212af4c7e586a44cca13664703e03`.

#### Блок портфолио

Проверено:
- callbacks `portfolio:view`, `portfolio:upload`, `portfolio:item:*`, `portfolio:file:*`, `portfolio:resume`;
- порядок подключения participant router;
- старые participant add-ons, которые дублировали профиль, достижения, портфолио и task callbacks.

Найдено:
- `portfolio_navigation.py` перехватывал `portfolio:upload` раньше реального upload-flow;
- `participant/addons.py` хранил неподключённые дубли профиля, достижений и портфолио;
- в `growth.py` оставались старые task callbacks, хотя задачи уже принадлежат `task_block2.py`.

Сделано:
- `portfolio:upload` теперь открывает реальную загрузку достижения в `growth.py`;
- просмотр портфолио остаётся в активных owner-модулях кабинета/достижений;
- старые duplicate portfolio/task add-ons удалены и закреплены системным аудит-тестом.

Проверка:
- `python -m pytest tests/test_participant_tasks_cabinet.py tests/test_full_bot_flow.py tests/test_system_wide_audit.py tests/test_v2_scenarios.py` — 29 passed;
- `python -m pytest` — 150 passed;
- `git diff --check` — успешно.

PR: #82.

Merge commit: `cc499beb83642a5f43aca8f16dc0344de822a2cc`.

CI:
- Tests: success on `c57cc94dacf70a77d449d294138e06acef836ad1`;
- Bot checks: success on `c57cc94dacf70a77d449d294138e06acef836ad1`.

### Дополнительный продуктовый блок. Заявка участника и admin user card

Проверено:
- регистрационный flow с сохранением `photo_file_id` и соцссылки;
- отправка заявки администраторам после регистрации;
- активные callbacks `admin:application:*`, `admin:approve_user:*`, `admin:reject_user:*`;
- админские callbacks выбора участника `admin:user:*` из списков, поисков, мероприятий и связанных разделов.

Найдено:
- заявка администратору отправлялась как текст без сохранённого фото участника;
- соцсети не были единым обязательным элементом admin card;
- `admin:user:*` мог показываться разными реализациями карточки;
- approval был продублирован в `approval_bonus_fix.py` и `panel.py`;
- повторная обработка уже отклонённой заявки не была явно закрыта общим правилом.

Сделано:
- добавлен единый presenter `app/services/admin_user_card.py`;
- заявка и карточка участника теперь показывают фото первым сообщением, если `file_id` есть;
- при отсутствии фото карточка явно пишет `Фото: не загружено` и не падает;
- карточка включает имя, Telegram, возраст/дату рождения, роль, статус, департаменты, направления, баллы, портфолио и соцсети;
- регистрация отправляет администраторам полноценную карточку заявки через сохранённый `file_id`;
- `admin:application:*`, `admin:user:*` в active profile/rights handlers переведены на один presenter;
- добавлен `app/services/application_review_service.py` для единого approve/reject;
- повторный approve/reject защищён, уведомления не дублируются.

Тесты:
- добавлен `tests/test_admin_user_card.py`;
- обновлён контракт получателей admin notifications.

Проверка:
- `python -m pytest tests/test_admin_user_card.py tests/test_admin_notification_recipients.py tests/test_full_bot_flow.py tests/test_system_wide_audit.py` — 23 passed;
- `python -m pytest` — 155 passed;
- `git diff --check` — успешно.

PR: #84.

Merge commit: `c9af904bc305dcaba574ea8f6502c8434a7e838d`.

CI:
- Tests/Bot checks: success on `ecbf3f5247777ff13b9efa78429cf39548b5d4da`.

Следующий блок:
- chat access / join approval / restrictions.

### Дополнительный продуктовый блок. Chat access / join approval / restrictions

Проверено:
- текущий `/bind general/internal/external/leaders/channel`;
- хранение chat IDs в `Settings`, `AppSetting`, `ChatGreeting`;
- старый group moderation flow в `app/handlers/chat.py`;
- Telegram events `chat_join_request` и `new_chat_members`;
- точки изменения пользователя: approval, role change, block/unblock, archive/unarchive.

Найдено:
- доработанная модерация могла удалять сообщения, но не управляла Telegram permissions;
- `leaders`-чат раньше использовал ban/unban вместо ограничения права писать;
- join request не обрабатывался как отдельный Telegram flow;
- не было следа pending join request для пользователя, который уже запросил вход, но ещё не одобрен администратором;
- смена роли/блокировка/архив не пересчитывали права в уже привязанных чатах.

Сделано:
- добавлен единый сервис `app/services/chat_access_service.py`;
- доступ определяется по существующим `/bind` chat IDs: `general`, `internal`, `external`, `leaders`;
- `general` открыт всем approved пользователям;
- `internal` и `external` зависят от выбранного департамента;
- `leaders` открыт только privileged roles и администраторам;
- незарегистрированные и не approved пользователи получают понятное личное сообщение и не получают доступ;
- rejected/blocked/archived/wrong role users отклоняются или ограничиваются;
- новый `chat_join_request` handler использует `approve_chat_join_request` / `decline_chat_join_request`;
- обход через прямое попадание в чат закрывается через `restrict_chat_member` с выключенными send permissions;
- после approval/смены роли/блокировки/архива запускается синхронизация прав по привязанным чатам;
- добавлена таблица `pending_chat_join_requests` и миграция `0011_pending_chat_join_requests`.

Тесты:
- добавлен `tests/test_chat_access_service.py`;
- расширен `tests/test_stability_bindchat_projects.py`.

Проверка:
- `python -m pytest tests/test_chat_access_service.py tests/test_stability_bindchat_projects.py tests/test_full_bot_flow.py tests/test_system_wide_audit.py` — 28 passed;
- `python -m pytest` — 163 passed;
- `python -c "... alembic upgrade head"` на локальной SQLite async базе — успешно;
- `git diff --check` — успешно.

PR: #86.

Merge commit: `645f2cf98f32142ef3ec27f7166270c49626a69b`.

CI:
- Tests/Bot checks: success on `3ea4b390b7756c08a60ad089a9688734f6186ef3`.

Следующий блок:
- рассылки и уведомления.

### Этап 7. Рассылки и уведомления

#### Блок 1. Устойчивое ядро массовых рассылок

Проверено:
- `app/services/notification_service.py`;
- массовая админская рассылка `admin:broadcast`;
- одобрение лидерской рассылки;
- текущие прямые Telegram sends и существующий `safe_send`.

Найдено:
- старый `broadcast()` отправлял последовательно;
- получатели не дедуплицировались на уровне сервиса;
- `RetryAfter` и временные Telegram/network/server errors не retry-ились отдельно от permanent failures;
- администратор видел только `sent/failed`, без дублей и типа ошибок.

Сделано:
- добавлен `broadcast_detailed(...)` с дедупликацией получателей;
- добавлен лимит параллельности через `asyncio.Semaphore`;
- `TelegramRetryAfter`, network и server errors retry-ятся ограниченно;
- `Forbidden/BadRequest` считаются permanent failures и не retry-ятся;
- старый `broadcast()` сохранён совместимым и возвращает `(sent, failed)`;
- массовая админская рассылка и одобренная лидерская рассылка показывают total, sent, failed, duplicates, temporary/permanent failures.

Тесты:
- добавлен `tests/test_broadcast_service.py`;
- расширен контракт `tests/test_admin_notification_recipients.py`.

Проверка:
- `python -m pytest tests/test_broadcast_service.py tests/test_admin_notification_recipients.py tests/test_full_bot_flow.py tests/test_system_wide_audit.py` — 25 passed;
- `python -m pytest` — 170 passed;
- `git diff --check` — успешно.

PR: #88.

Merge commit: `792f3928bdef73f591479ed423d5edc3710611b0`.

CI:
- Tests/Bot checks: success on `6d6c5258503b2e6cd67cd4b2916eee69e0eeffcc`.

Следующий блок:
- аудит автоматических уведомлений и прямых send_* с файлами/медиа.

#### Блок 2. Медиа и файловые уведомления

Проверено:
- прямые `bot.send_photo/send_video/send_document` в task submissions;
- отправка proof-файлов активностей после мероприятий;
- отправка файла проекта на рассмотрение;
- публикация event cards с poster photo в чат;
- текущие silent `except Exception: pass` вокруг Telegram media sends.

Найдено:
- часть media sends молча глотала любые ошибки;
- сбой доставки файла одному админу не фиксировался в результате;
- project submission мог упасть на прямом `bot.send_document` после уже сохранённой заявки;
- event card fallback был без логируемого safe wrapper.

Сделано:
- добавлены `safe_send_photo`, `safe_send_video`, `safe_send_document`;
- task result media пересланы через safe helpers с подсчётом доставок/ошибок;
- event activity proof media пересланы через safe helpers с подсчётом доставок/ошибок;
- project review document отправляется через safe document helper;
- event cards в чат используют safe photo/text helpers;
- silent media failures заменены на контролируемый fallback/уведомление.

Тесты:
- добавлен `tests/test_media_notifications.py`;
- обновлён `tests/test_event_photo_contracts.py`.

Проверка:
- `python -m pytest tests/test_media_notifications.py tests/test_event_photo_contracts.py tests/test_broadcast_service.py tests/test_full_bot_flow.py tests/test_system_wide_audit.py` — 29 passed;
- `python -m pytest` — 173 passed;
- `git diff --check` — успешно.

PR: #90.

Merge commit: ожидает merge.

CI:
- Tests/Bot checks: success on `1bb38b3b71f34582e45ef458d3b8adf7ef10243a`.

Следующий блок:
- survey/event/chat broadcast recipients and notification deduplication.
