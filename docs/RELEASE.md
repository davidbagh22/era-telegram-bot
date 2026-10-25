# Выпуск игр: имена, команды и личный бот

## Изменение поведения

Раньше тема содержала отдельные анонимные вопросы, подтверждения и результаты. Теперь одиночные форматы открываются в личном боте, а командная игра имеет одну сохраняемую карточку. В ней видны имена из Telegram, явные Telegram ID, автоматически сформированные команды, готовность, принятые ответы, очки и победители. Игра требует одобренного активного профиля ЭРА. Приватные данные анкеты не используются в публичном составе.

В личном боте: /games, deep link /start games и «Досуг → Мои игры»; доступны одиночные игры, последние результаты и переход к собственной команде. Старые кнопки поддерживаются, слепых повторных публикаций нет. Если Bot API не показывает старый закреп, новая редакция навигации отправляется один раз с отдельным ключом games-menu-identity-v2; неизвестный исход отправки не повторяется. Старый анонс games-notification-v1 не переотправляется.

## Проверки и исходное состояние

- Исходный production SHA: 72187135aaedd3e8b4b018965feaff1b22ffa844.
- Последняя подтверждённая backup/restore: 16.10.2026 05:50:23 UTC; рабочая база не восстанавливалась и не очищалась.
- Миграция 0061_notification_message после 0060_media_chat_bigint добавляет nullable bigint message_id в notification_deliveries. ID и статус отправки подтверждаются одной транзакцией; старые receipts с NULL читаются без догадок. Поля игровых комнат остаются в существующем JSON. Миграция additive; при rollback кода колонка сохраняется.
- Локально: 140 tests и 8 subtests passed (игры, shared card, expiry/restart, ошибки Telegram, доступ, deep links, навигация). ruff E9/F, compileall и validate_general_chat_content прошли.
- Полный CI на окончательном head и Render live обязательны до приёмки; не заменяются этим документом.

## Production acceptance

1. Проверить CI на точном PR head; не объединять конкурирующие draft PR.
2. Дождаться автоматического Render deploy по checksPass; проверить /health с итоговым main SHA и /ready.
3. Проверить games-menu-card AppSetting: actual message_id и confirmed; существующие темы/thread_id и receipts games-menu-v1 / games-notification-v1 должны сохраняться без повторного анонса.
4. Проверить новый instance на ошибки scheduler/игр. Startup не должен переписывать игровые закрепы регистрационным текстом.
5. Ручной Telegram E2E выполняет владелец: два зарегистрированных участника вступают одной кнопкой, видят свои команды/имена, заканчивают дуэль; одиночная игра открывается в личном боте.

## Откат

Откатить код на исходный SHA через Render, не выполнять downgrade БД и не удалять app_settings, пользователей, баллы или историю. FEATURE_GAMES=OFF временно останавливает игровые callbacks и запуск, GAMES_REWARDS_ENABLED=false отдельно останавливает награды. Старый код игнорирует дополнительные поля состояния. При unknown Telegram send outcome карточка не отправляется повторно автоматически; нужен реально наблюдаемый message_id для сверки. При отсутствии прав на pin — не более трёх попыток, без unpin/delete чужих сообщений.

Итоговый SHA, CI run IDs, Render deploy и HTTP-проверки фиксируются в merged PR после фактического выпуска, чтобы не писать выдуманный production SHA до merge.

## Подтверждение игрового этапа #337

- Merge SHA: c3cf126b3bd2bd8580f21a22df89e8c585b40661; final PR head e768a7268ec5ef1db82ad81093c0e95fc8286c10, tree 80758ff59b0124819b3efb914b7551e9758910dd.
- Bot checks 38880266778 и Tests 38880266811: success. Оба прогона: 1674 passed, 1 skipped, 1 xfailed, 58 subtests. PostgreSQL migration/races, browser E2E, dependency audit и secret scan успешны.
- Дополнительный pre-release backup и isolated restore: success 16.10.2026 09:26:44 UTC, 1 545 104 bytes (повторный запуск штатного OIDC backup workflow).
- Merge выполнен только после CI и закрытия двух review findings. Render deploy dep-db8v9imq1p3s738oj3gg live 16.10.2026 09:57:27 UTC. /health и /ready HTTP 200, commit c3cf126, migration 0061_notification_message. games-menu-card confirmed, message_id 26355; navigation delivery attempt_count=1. Старый games-notification-v1 остаётся attempt_count=1, нового анонса нет. После live ошибок в журнале не обнаружено.

## Следующий этап: управленческая сводка и посещаемость в боте

- Расширен существующий system summary: 09:00 Europe/Moscow, ежедневный/еженедельный/месячный отчёт, стабильный snapshot периода, общий NotificationDelivery, manual refresh и агрегированный Excel. Права получателей проверяются по active admin / global analytics.view, адресный whitelist не расширяет права.
- Новый учёт game-result сохраняет реальные завершённые игры. Старые перезаписываемые комнаты не выдаются за полную историческую статистику.
- Attendance v2 использует текущие сессии, окно завершённого мероприятия, регистрацию и confirm_attendance. Native QR для ведущего, ввод кода в личном боте, серверные права, повтор без второй награды, закрытие окна. Старый QR механизм остаётся retired.
- Bot start/complete теперь вызывает тот же lifecycle, что API. Уведомления отправляются после commit через общую durable delivery; unknown outcomes не повторяются, rollback не создаёт уведомления. Старый RSVP callback не стирает ATTENDED.
- FEATURE_MANAGEMENT_REPORTS=TESTERS и FEATURE_ATTENDANCE_QR=TESTERS, отдельные разрешённые получатели/тестеры; default и пустое значение обоих флагов = OFF. Общий Mini App режим не меняется.
- Новых миграций сверх 0061 нет. Rollback к c3cf126 оставляет дополнительные AppSetting результаты/снимки/очередь и все баллы, регистрации и посещения.
- Полный текущий остаток и критерии реальной приёмки: MASTER_REMAINDER.md. Непроверенные пункты общего мастер-ТЗ не объявляются готовыми.

## Подтверждение управленческого/attendance этапа #338

- Merge SHA: `0a78bff13e2266308f1aa5b064d25862ab43e371`. PR #338 прошёл Bot checks и полный Tests workflow; включал чистые миграции, PostgreSQL concurrency gates для баллов/игр/отчётов, фронтенд, E2E и secret scan.
- Render service `srv-d91r1j7avr4c73fs8h00`, deploy `dep-db931mcs728c73bjhe40`, статус `live`, commit `0a78bff…`. После deploy проверены `/health` → HTTP 200 `status=ok`, commit `0a78bff`; `/ready` → HTTP 200 `status=ready`.
- Флаги отчёта и QR выставлены через Blueprint в TESTERS для выделенного администратора. Данные тестовых посещений и рассылок в production не создавались.

## Короткий native ввод мероприятия — PR #339

- Изменение: один редактор готового текста с фотографией, распознавание только однозначных даты/времени/места/лимита, редактирование в одной карточке, полный предпросмотр, публикация через существующий API и возобновляемый черновик. Расширенный мастер остаётся.
- Merge SHA: `50de3c7a39d0a90ad91ae98eff1bdccfde96b468`. PR #339 оба обязательных CI workflow завершились success; каждый: 1700 passed, 1 skipped, 1 xfailed, 58 subtests. E2E, PostgreSQL migration/races, frontend, dependency audit и secret scan успешны.
- Render deploy `dep-db93lqvavr4c73ctug6g` live. `/health`: HTTP 200, commit `50de3c7`; `/ready`: HTTP 200. После старта `system_diagnostic_runs` записал heartbeat `healthy`, score 100; PostgreSQL остаётся на migration `0061_notification_message`.
- Rollout ограничен `FEATURE_NATIVE_EVENT_COMPOSER=TESTERS`, собственным `NATIVE_EVENT_COMPOSER_TESTER_IDS` (администратор 1593868942); default OFF, пустой список не наследует общие feature testers. Расширенный мастер сохранён, личные рассылки выключены.
- Локальные targeted проверки: 28 тестов вместе с безопасным медиа sender прошли, Ruff и compileall прошли; SQLite проверил повторное редактирование одного Event draft без дубля, пропуск старых публикаций и снятие лимита. Caption режется после HTML escaping с сохранением целых entity.
- Реальный пользовательский smoke в Telegram владельцем ещё не выполнен. ИИ не входил в Telegram и не создавал тестовых мероприятий или регистраций в production. До проверки владельцем флаг остаётся в TESTERS.
- Последняя подтверждённая копия/изолированное восстановление: 16.10 09:26:44 UTC до серии релизов. В #339 схемных миграций нет; новой копии непосредственно перед ним не создавали.

## Native operations: #342–#344, 17.10.2026

Сводка изменений — IMPLEMENTATION_REPORT_2026_10_17.md; пользовательский вход — /start → «Админ-сводка» / «Заявки», /admin → обращения/редакция/рассылки. Финальное подтверждение runtime SHA/deploy/CI/health/flags — в описании PR #344 после Render live; до этого release не считать принятым.

Схема остаётся 0061_notification_message. Перед выпуском подтверждён encrypted backup + isolated restore 17.10 04:08:35 UTC (healthy source 36de387). Переменная MANAGEMENT_REPORT_RECIPIENT_IDS должна оставаться валидным JSON: [] для отсутствующего allowlist, не пустая строка.

Откат: поставить редакционную очередь на паузу, выключить новый SLA, остановить операционные подтверждения campaigns и вернуть предыдущий подтверждённый код. Сохранить JSON [] в Render при откате; Git-revert не должен возвращать ошибочное value: "". Никакого удаления questions/markers/ledger или down migration. Старый код не возобновляет answer_pending/paused; после возврата исправленной версии используют прежние ключи. Отменённые campaigns не подтверждать заново через старый код. Не публиковать literature content IDs через старый generic publisher.

TESTERS rollout QR/composer/quick registration/SLA сохраняется. Редакционная очередь выключена, пока редактор не проверит материал и не включит её. Профильные реальная игра/QR/event canary и плановая доставка сводки ещё требуют фактической проверки владельцем.
