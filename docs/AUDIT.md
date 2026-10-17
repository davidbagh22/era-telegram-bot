# ЭРА: проверенный исходный срез и исправления

Дата: 16.10.2026. Репозиторий `davidbagh22/era-telegram-bot`. Исходный main и production: `72187135aaedd3e8b4b018965feaff1b22ffa844` (PR #336). Этот документ отделяет наблюдаемые факты от ещё не выполненной приёмки мастер-ТЗ.

## Production и доступ

- Render `srv-d91r1j7avr4c73fs8h00`, workspace `tea-d91quq1o3t8c73ehphh0`: live, deploy `dep-db8h43g4ufvs73aq1is0` с 15.10.2026 17:52:07 UTC. Проверено повторно 16.10.
- Web service starter, Docker, Frankfurt, main, `autoDeployTrigger=checksPass`, health check `/ready` (фактические параметры Render).
- PostgreSQL `dpg-d91r19vavr4c73fs837g-a`: migration `0060_media_chat_bigint`. Доступен только read-only SQL через коннектор; прямого доступа к production-секретам не использовали.
- Точный COUNT(*) всех 124 public-таблиц: [отдельный срез](AUDIT_PRODUCTION_COUNTS_2026_10_16.md). В частности users=51, events=9, points=476. Системные оценки pg_stat не используются как количество участников.
- Backup: daily success 16.10.2026 05:50:23 UTC, 1 544 080 bytes, `restore_verified_at=05:50:23 UTC`; предыдущий daily также success. Восстановление production-копии уже выполнено существующим OIDC workflow в изолированный PostgreSQL, а не в рабочую БД.
- Предыдущий релиз: Tests #38778143440 и Bot checks #38778143316 завершены success на head `c06fa57ba41ba88174225546a07332a445938e12`; production — squash SHA выше. 1651 passed, 1 skipped, 1 xfailed; это результат предыдущего релиза, не текущей ветки.
- Вход в Telegram владельца не разрешён и не выполнялся. Ручную проверку под реальными участниками нельзя объявлять выполненной на основании unit-тестов.

## Архитектура и точки входа

| Участок | Файлы и назначение |
|---|---|
| Production | Dockerfile → scripts/start_production.py → Alembic под advisory lock → app.webapp:app |
| Webhook и HTTP | app/webapp.py: lifespan, Telegram update dispatcher, /health, /ready; app/api/v1/router.py |
| Bot | app/bot.py: create_dispatcher, Redis FSM и изоляция обновлений; app/handlers/emergency.py владеет обычным /start |
| Регистрация | app/handlers/registration.py, app/repositories/users.py, User, RegistrationDraft; существующие анкеты сохраняются |
| Доступ | app/middlewares/auth.py, app/services/leadership_permission_service.py и действующая permission matrix; роли не создаются параллельно |
| Мероприятия | app/services/event_*; API/admin wizard; Event, EventRegistration, EventExperience, attendance sessions/proofs |
| Начисления | app/services/points_service.py, PointTransaction (таблица points); game_rewards_service вызывает этот ledger |
| Отправка | notification_service.safe_send_once, NotificationDelivery; general_topics_service маршрутизирует по сохранённым thread_id |
| Публикации мероприятий | event_publication_service: durable состояния и uncertain; повторная доставка планировщиком |
| Литература | book_club_service, literature_launch_service, general content queue; отдельный scheduler уже существует |
| Игры | era_game_room.py, game_formats.py, game_content.py, game_rewards_service.py; AppSetting хранит комнаты и историю показов |
| Проекты/задачи | project_* и task_* services, handlers/admin и handlers/leader; существующие права, согласования и баллы |
| Эксплуатация | system_health_service, system_scheduler, backup_history, system_incidents; GitHub OIDC backup/restore workflow |
| Mini App | frontend + API уже существуют; не считать наличие исходников доказательством включения в Telegram |

Полный список команд и планировщика по AST текущего кода: [inventory](AUDIT_CODE_INVENTORY.md). Устаревшие fallback-обработчики нельзя удалять только из-за похожих имён. В частности start.py документирует, что emergency.rescue_start перехватывает /start раньше него. При аудите исправлено обнаружение router-импортов `from app.handlers.module import router as alias`, иначе скрипт ошибочно считал leisure:home и bookclub:home отсутствующими.

## Флаги

| Переменная | Default app/config.py | Подтверждённое состояние |
|---|---|---|
| FEATURE_GAMES | OFF | ALL, выпущено #336; успешные игровые комнаты production и Blueprint |
| GAMES_REWARDS_ENABLED | false | true, выпущено #336 и подтверждены начисления в общем ledger |
| FEATURE_AUCTIONS / REWARDS / ERA_PRO / SURVEYS / VECTOR / REFERRALS / MEDIA / ROLE_RECRUITMENT | ALL | Фактический env Render каждого отдельно не проверен; defaults не выдаются за env |
| DEV_AUTH_ENABLED | false | Фактический env не извлекался; production safety gate проверяется тестами |
| FEATURE_TESTER_IDS | [] | Значения не публикуются; TESTERS routing покрывается тестами |
| Mini App URL | Зависит от конфигурации | Повторно не включался; проверка Telegram initData должна оставаться обязательной |

## Чаты и темы

| Сохранённый ключ | thread_id |
|---|---:|
| general_forum:-1002973371133:announcements (Мероприятия) | 26205 |
| general_forum:-1002973371133:notifications (Оповещения) | 26206 |
| general_forum:-1002973371133:literature | 26216 |
| general_forum:-1002973371133:games (🎮 Интерактив) | 26296 |
| leaders_forum:-1002948316715:tasks | 21717 |
| leaders_forum:-1002948316715:pulse | 21719 |
| leaders_forum:-1002948316715:important | 21721 |

Проверено read-only по app_settings. ID и названия не меняются. Отдельная тема «Общение» не подтверждена и не создавалась. Ссылки департаментов уже есть в render.yaml и directions_announcement; выполнение конкретной доставки проверяется по NotificationDelivery, а не наличию ссылки в исходниках.

## Игровые форматы

| Согласованное название | GameMode | Режим после исправления UX | Результат |
|---|---|---|---|
| Быстрый квиз | solo_quiz | Личный бот, 5 вопросов | Индивидуальный счёт |
| Командный квиз | team_quiz | Общая команда, 2–8 игроков | Состав и результат каждого |
| Правда или миф | true_or_myth | Личный бот | Ответ и пояснение |
| Угадай страну | guess_country | Личный бот | Подсказки уменьшают очки |
| Хронология | chronology | Личный бот | Проверка порядка событий |
| Словесная цепочка | word_chain | Личный бот | Проверка последней буквы |
| Ассоциации | associations | Личный бот | Последовательные подсказки |
| Логика | logic | Личный бот | Проверяемый ответ |
| Культурный блиц | culture | Личный бот | Вопрос и пояснение |
| Память | memory | Личный бот | 5 секунд показа и скрытие |
| Командная дуэль | team_duel | Две автоматически балансируемые команды | Имена, составы, очки, конкретные победители |

В production исходного среза 12 последних комнат: 10 finished, 2 expired. Это комнаты, а не число всех исторических игр/игроков: ключи переиспользуются. История начислений и показов сохраняется отдельно. Банк контента и ограничения 180 дней уже реализованы; объём и уникальность подтверждаются tests/test_games_question_bank.py. Единая бесконечная история игр и тренды пока не измеряются существующими overwriting room keys — не показывать её как точную аналитику.

## Подтверждённые дефекты и исправления текущего этапа

| Приоритет | Дефект | Действие / доказательство |
|---|---|---|
| P1 | Игры/победы анонимны; нельзя понять составы | Telegram display name + явный Telegram ID, именованные составы, персональные результаты; данные анкеты не публикуются |
| P1 | Каждое действие засоряет общую тему новым сообщением | Одна сохраняемая карточка комнаты; join/ready/ответ/результат/expiry редактируют её |
| P1 | Можно участвовать без зарегистрированного профиля | Проверка одобренного, активного User в каждом callback; повторная проверка всего состава перед стартом |
| P1 | Ручной выбор стороны не показывает команду и даёт путаницу | Единое «Присоединиться», атомарный выбор меньшей команды; legacy buttons не позволяют менять сторону |
| P1 | Одиночные игры перемешиваются с командами | Public URL → /start game_* в личном боте; /games и «Досуг → Мои игры» показывают собственные игры и команду |
| P1 | Startup мог перезаписать любой bot-owned pin регистрационным текстом | Проверять идентичность регистрационной карточки; игры и чужие закрепы не редактировать |
| P1 | Закреп не восстанавливается адресно | Принимать только реально полученный из Bot API game pin с верным owner/thread; сохранять message_id, редактировать его, pin без уведомления; 3 попытки; если старый ID невозможно наблюдать, одна новая редакция меню через общий ledger, без повторного анонса |
| P2 | 20 секунд на готовность слишком мало | 90 секунд, общий предел набора 3 минуты; выход сбрасывает готовность и перебалансирует команды |
| P2 | Нет видимого завершения зависшей карточки | Scheduler закрывает сохранённую комнату и снимает кнопки; повторный запуск не создаёт сообщений и баллов |

Квитанция NotificationDelivery теперь сохраняет Telegram message_id вместе со статусом sent (additive 0061_notification_message). Проверены остановка после durable send до сохранения pin state и однократная замена подтверждённо удалённого сообщения.

## Открытые PR и риски

Повторно проверены 7 открытых draft PR: #319 (audit baseline), #283 (старые миграции/Vector), #264 (старый UI/локализация), #219 (старый конструктор/UI), #250/#253/#282 (включают недопустимые автоматические permission writes). Они не объединялись. Конкурирующие исправления bigint и format уже перенесены в #336; старые цепочки Alembic повторно не вливаются. #327/#334 ранее рассмотрены при выпуске безопасности; новые игровые изменения не вызывают ban/unban/restrict.

## Матрица мастер-ТЗ и следующий исполняемый остаток

| Модуль | Статус | Доказательство / что остаётся |
|---|---|---|
| Игры 11 форматов | Исправлено в ветке, ожидает CI/Render | Сценарии всех механик, реальная БД тестов, негативные permissions, один message_id; production подтверждать отдельно |
| Мероприятия / быстрый composer / outbox | Частично | #336 закрывает composer и публикацию; полный end-user сценарий из текущего мастер-ТЗ повторно не пройден |
| Баллы | Реализовано, тестируется | Общий ledger, уникальные ключи, PostgreSQL race gates; не значит, что все ручные действия уже проверены владельцем |
| Регистрация / профиль / согласия | Частично | Существующий 17-полевой поток и черновики сохраняются; быстрая регистрация/доработка после минимального профиля требуют отдельного разбора |
| QR посещаемость | Нет в актуальном live UX | event_qr_service намеренно retired; tests/test_qr_system_audit.py это закрепляет. Мастер-ТЗ требует безопасного нового QR поверх действующей attendance session, без оживления старых ссылок |
| Одноразовый код / ручное посещение | Есть реализация | event_attendance_service и UI/API; полный production сценарий не объявлен проверенным |
| Рассылки | Частично | Durable delivery + RetryAfter + uncertain уже есть; кампании/редактирование требуют отдельной матрицы прав и сценариев |
| Литература | Частично | Рубрика и расписание существуют; повторная проверка отправки, очереди и редакторского согласования по фактическим receipts |
| Департаменты | Частично | Ссылки/публикация реализованы; нельзя считать все сценарии автоматизации завершёнными |
| Ежедневная аналитика 09:00 МСК | Не завершено по новому ТЗ | Есть system summary 09:30 по timezone settings (Asia/Yerevan); это не полная управленческая сводка 09:00 МСК. Расширять существующий отчёт, не создавать вторую систему рассылки |
| Проекты и задачи | Частично | Существующие workflows и scoring reconciliation; проверить 72ч, согласующих и весь цикл из ТЗ |
| Обращения / SLA | Частично | Модели/обработчики существуют; нельзя утверждать SLA 24ч без проверки scheduler/receipts |
| Роли / безопасность | Частично | Существующая permissions matrix; защищённые игровые действия проверены на сервере, остальные права отдельно по отрицательным тестам |
| Backup / восстановление | Подтверждено сегодня | backup_history success + restore_verified_at; не означает испытание полного disaster recovery за целевой RTO |
| Health / readiness / мониторинг | Подтверждено исходным релизом | Реальные HTTP endpoints и diagnostics; после выпуска перепроверить ожидаемый SHA |
| Mini App / локализации / сертификаты / интеграции | Не приняты полностью | Новое включение не выполнялось; вторичные функции идут после P0/P1 |

Этот остаток — ограничения текущего среза, не заявление о полной готовности. После выпуска игр: расширение существующей управленческой сводки, безопасная QR attendance поверх актуального кода, затем проверка оставшихся пользовательских сценариев. Конкретные изменения и релизы фиксируются в RELEASE.md и PR, без повторного общего аудита уже доказанных частей.

## Актуализация после релизов 16.10.2026

Начальные факты выше относятся к исходному срезу `72187135`; статусы игр/QR/сводки ниже заменяют соответствующие прежние строки матрицы. Значения живых секретов не читались.

| Модуль | Актуальный статус на production, code SHA `50de3c7` | Проверенное доказательство / остаток |
|---|---|---|
| Игры: 11 форматов | Развёрнуты | #337, migration 0061, закреп/ledger confirmed; live SHA `c3cf126` до следующего релиза. Полный CI: 1674 passed; ручная игра реальными участниками остаётся владельческой приёмкой. |
| Управленческие отчёты | Развёрнуты в TESTERS | #338, ежедневные/недельные/месячные снимки и общий sender. Merge `0a78bff`; следующий main CI: 1691 passed, 1 skipped, 1 xfailed, 58 subtests; E2E, PostgreSQL gates, frontend, secret scan успешны. |
| QR посещаемость | Новый v2 развёрнут в TESTERS | #338 использует текущие attendance session, регистрацию и points_service; закрытие окна и повторная защита реализованы. Нужен владелец для реального сценария; production посещения не подделывались. |
| Создание мероприятий в native боте | Развёрнуто в TESTERS | #339: один экран текста/фото, редактируемые поля, реальный предпросмотр, возобновляемый draft, существующие Event API/outbox. Ручной сценарий владельцем ещё нужен. |
| Регистрация/профиль, литература, кампании, проекты/SLA | Частично/не приняты | Требования MASTER_REMAINDER.md; не отмечать готовыми по наличию отдельных сервисов. |
| Права и Telegram permissions | Проверены по указанным изменениям | #327 закрыт без merge; #334 merged. Автоматические overrides чужих ограничений отключены. Другие привилегированные действия требуют отдельной отрицательной матрицы. |
| Backup/restore | Последняя подтверждённая копия до текущей серии релизов | 16.10 09:26:44 UTC, 1 545 104 bytes, изолированное восстановление success. Это не полное DR/RTO испытание и не новая копия непосредственно перед каждым последующим релизом. |
| Health/readiness/scheduler | Проверено после #339 | `/health` HTTP 200, `commit=50de3c7`; `/ready` HTTP 200. `system_diagnostic_runs`: heartbeat healthy/100 в 14:56:38 UTC. Migration `0061_notification_message`. Render deploy `dep-db93lqvavr4c73ctug6g` live. |

Production #339: SHA `50de3c7a39d0a90ad91ae98eff1bdccfde96b468`; Bot checks и Tests на финальном PR head, а также post-merge main Bot checks успешно завершились (каждый: 1700 passed, 1 skipped, 1 xfailed, 58 subtests), E2E/PostgreSQL/frontend/secret scan успешны.

Из наблюдений после deploy: повторяется startup error `Chat menu button mismatch` (16.10 14:13:50 и 14:56:35 UTC): Bot API возвращает тип `web_app`, но read-back проверка не подтверждает актуальную кнопку. Это не изменялось PR #338/#339; проверить Mini App URL/read-back отдельно, не включать Mini App шире. Последний heartbeat healthy. Резервная копия 16.10 09:26:44 UTC и изолированное восстановление прошли до серии релизов, свежая копия до #339 не запускалась; в #339 новых миграций нет.

Путь `Codex could not read the local image ... No such file` относился к временному upload path предыдущего сеанса; вложения этого диалога доступны, сообщение само по себе не дефект бота.

## 17.10.2026: native operations и надёжность очередей

Эта актуализация уточняет исходный срез выше; полный code inventory и counts не пересоздавались. После #342 доступны direct admin buttons/заявки/сводки и обновлённые игры. #343 исправляет fresh backup/rerun. #344 добавляет reviewed editorial queue, native support/atomic intake, SLA и campaign controls. Соответствующие статусы и остаток: FUNCTIONAL_MATRIX.md, MASTER_REMAINDER.md, IMPLEMENTATION_REPORT_2026_10_17.md.

Точки входа: app/handlers/admin/{commands_ready,dashboard_block_a,application_review_bot,literature_editor,support_bot,campaign_control}.py; participant/questions.py. Сервисы: admin_analytics_service, application_review_service, support_service, book_club_service, admin_broadcast_service, scheduler_service. Общий transport: bot.create_bot → TelegramDeliveryMiddleware → существующий safe_send_once/NotificationDelivery.

Новых таблиц/миграций нет; production schema перед этим выпуском — 0061_notification_message. Source/delivery markers находятся в существующем AppSetting. Pending intents удаляются после terminal receipt, domain questions/history и source keys сохраняются. Дополнительные scheduler jobs: application-notices, support-answer-delivery, review-sla-reminders, book-club-editorial-recovery. Отчёты используют 09:00 Europe/Moscow и существующий recovery.

Ожидаемые значения Blueprint: management reports ALL; quick registration/native composer/QR/SLA TESTERS; editorial queue disabled в БД до редакторского включения. Значения по умолчанию новых Settings flags OFF. Фактические runtime flags проверяются по whitelist startup log; итоговый факт, CI/runtime SHA и live фиксируются в описании PR #344 после деплоя, без чтения секретов.

Обнаруженный P1 выпуска: MANAGEMENT_REPORT_RECIPIENT_IDS="" вызывал Pydantic SettingsError и update_failed. Значение исправлено на "[]" в Render и Blueprint; добавлен env regression test. Исходный сервис после исправления подтвердил live/health, backup restored 17.10 04:08:35 UTC. Другой P1: исходное создание обращения отправляло Telegram до commit; заменено атомарным intake/source key + durable notice, с серверной повторной проверкой прав.

#327 закрыт без merge; #334 объединён и сохраняет защиту модераторских решений. Новые native approvals не вызывают unban/restrict. Полная delegated access проводка не объявляется готовой. Реальных игроков/мероприятий/посещений для проверки не создавали; Telegram владельца не использовали.
