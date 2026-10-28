# ЭРА — актуальная контрольная точка, 28.10.2026

Этот файл заменяет устаревшие сводки. История сохранена в Git: предыдущий файл на c0102c767910d20c3c5d8e295da871d703ff57f1. Перед продолжением перечитать main, PR и Render; не повторять завершённые изменения.

## Точные версии и CI

- Текущий main: `c0102c767910d20c3c5d8e295da871d703ff57f1` (#462).
- Подтверждённый LIVE: `deeb2efc214a0e52d1d073c519205787d261b0ce` (#460), deploy `dep-dbgj9ca9lscs73bd3aog`, LIVE27.10 23:34:18 UTC.
- Новый код #461/#462 ещё НЕ подтверждён LIVE. autoDeploy=yes, checksPass; ручной deploy не запускать.
- Main CI c0102c7 на последней проверке: test=in_progress, postgres-migration=success, e2e=in_progress, frontend=success, secret-scan=success.
- #461 MERGED после6/6 success, HEAD `0bc9044a12a2ee34aa0160ef7fe1f972bb670726`, merge `414d85533600b5c64fd3aa78944c4a43a5353dc2`. Полный Bot checks test:2215 passed/275 subtests/1 skipped; оба test jobs success, e2e/PG/frontend/secret-scan success.
- #462 MERGED после6/6 success, HEAD `4b8c8cb2dc207c4bd090343a1e490b573259118f`, merge текущий main. Новый обязательный PostgreSQL probe8 конкурентных страниц подтверждён в успешном job122538822823.
- #463 OPEN, HEAD `b83153a190d808978c790f8745be37704c4e4671`: ВСЕ6 checks success при последней проверке; merge ещё не выполнялся.
- #464 OPEN, HEAD `3428fdec44809c19f5d53f2f069101314ee9a68d`: frontend/e2e/postgres-migration/secret-scan success; оба test jobs выполнялись. Не объединять по4/6.
- Обе ветки последовательно включают предыдущие изменения. Перед каждым merge заново проверить точный HEAD, mergeable, все обязательные CI и review threads; использовать expected_head_sha. Юридический draft#364 не объединять как утверждённые условия.

## Реально выполнено

1. #461: исправлены старые тесты и PostgreSQL fixtures под намеренно строгую проверку Tasks receipt для plain Пульс/Важно. Runtime guard не ослаблялся. Новая интеграционная проверка подтверждает отсутствие Telegram-вызовов и delivery receipt при missing/uncertain панели. Review finding устранён, thread resolved. Локально66 tests/68 subtests pass.
2. #462: воспроизведена блокировка21-го события за20 постоянно pending анонсами. Добавлен сохраняемый курсор с обходом до20 записей, возвратом к старым pending и PostgreSQL advisory lock между работниками. Прежние4 доставки/идемпотентные receipts сохранены; курсор фиксируется до Telegram. Локально до изменения2 новых теста failure, после17 event regression tests pass. PostgreSQL8-worker probe success.
3. #463: длинные нативные карточки/emoji разбиваются существующим escaped_text_parts по UTF-16, пользовательские символы экранируются, HTML задан явно. Caption до1000, сообщения до4000, кнопки только на последнем фрагменте, topic сохраняется. Отказ фото даёт весь текст, отказ сообщения останавливает последующие части. Необязательный parse_mode photo helpers сохраняет старый контракт остальных клиентов. Локально25 tests/2 subtests плюс25 общих notification/event tests pass.
4. #464: сохранённые boolean/float/отрицательные/повреждённые thread_id больше не становятся маршрутом и не создают замену существующей темы. Положительные числовые строки и JSON-объекты поддержаны. Сохранённая повреждённая запись не изменяется. Первичная настройка без записи сохранена. Локально27 tests/15 subtests pass; финальная прямая проверка маршрутов8 tests/15 subtests pass.
5. Для всех изменений correctness ruff E9,F и diff-check success. Новых миграций нет. Код/тесты/PR действительно сохранены в GitHub, реальные Telegram-сценарии не имитировались.

## Production и резервные копии

- На подтверждённом LIVE /health200 commitdeeb2ef, /ready200, /app/200.
- Без токена401: /api/v1/admin/analytics/v2, /api/v1/admin/analytics/full-report.xlsx, /api/v1/admin/analytics/executive-report.pdf, /api/v1/admin/analytics/executive-report.xlsx, /api/v1/media/workspaces. Вымышленные URL с404 не засчитывать проверкой защиты.
- После LIVE ошибки app и request500/502/503 не найдены на23:40:58 UTC; дополнительный app error read до23:57:58 UTC пуст. Это ограниченные интервалы, не сутки стабильности нового выпуска.
- ERA PostgreSQL `dpg-d91r19vavr4c73fs837g-a` available, external ipAllowList=[]; метрики23:00–23:30 UTC:10 connections. Hosted MCP SQL заблокирован закрытой сетью; сеть для диагностики не открывать. Commission DB отдельная.
- Backup run40459933608 от27.10 06:14:38 UTC, job122041859430 success: production snapshot через OIDC, restore на изолированном PostgreSQL18, encryption/verify и encrypted GitHub artifact — все success. Optional external S3 upload/restore skipped; не выдавать их за выполненные. Поверх production восстановление не запускалось.
- Запрошенное интерактивное ожидание CI было прервано пользователем; дальнейшие merge #463/#464 в этом ожидании не выполнялись. Незавершённые проверки не обходились.

## Следующая конкретная задача

1. Проверить #463: тот же HEAD,6/6 success, свежие review threads/mergeable; безопасно merge с expected SHA.
2. Проверить оба test jobs #464; при failure читать конкретные logs и исправить причину. После6/6 и review merge точного HEAD. Не перезапускать успешные jobs без причины.
3. Подтвердить ВСЕ5 CI последнего main и автоматический Render LIVE точного SHA. При отменённом промежуточном main CI следить за финальным SHA. Только после этого /health commit, /ready, /app,401 настоящих analytics/PDF/XLSX/media-workspaces, новые errors/5xx, PG и регрессии. До exact LIVE не объявлять выпуск.
4. Обновить checkpoint после выпуска. Этот отдельный checkpoint PR содержит документацию: не объединять его перед функциональными #463/#464 с устаревшим base; затем перенести актуальную сводку поверх нового main, сохранив более свежую работу.
5. Следующий реальный дефект стабильности: старый `app/handlers/admin/events_block6.py:broadcast_publish` пока использует интерактивный best-effort транспорт. Проверить конкурентное подтверждение, durable идемпотентность и восстановление неудачной доставки без настоящей публикации. Затем продолжать полный мастер медиа, ответственных по функциям, приватное портфолио,24/3ч напоминания и остальные требования. Наличие напоминаний мероприятий не доказывает медиа-напоминания.

## Файлы текущих этапов и воспроизведение

#461: app/services/leaders_topics_service.py; tests/test_leaders_plain_secondary_receipt.py; tests/test_leaders_chat_bind_safety.py; tests/test_leaders_topic_mode_routing.py; tests/test_leaders_native_workcenter.py; tests/test_pulse_announcement_delivery.py; scripts/postgres_leaders_workcenter_race.py.

#462: app/services/event_publication_service.py; tests/test_event_announcement_recovery_fairness.py; scripts/postgres_event_announcement_recovery_race.py; .github/workflows/ci.yml.

#463: app/services/event_card.py; app/services/notification_service.py; tests/test_event_card_transport.py.

#464: app/services/general_topics_service.py; tests/test_general_topics.py. Все этапы сохраняли docs/AI_TASK_STATE.md.

Команды (своё тестовое окружение, только фиктивный BOT_TOKEN):
```sh
BOT_TOKEN=0000000000:LOCALTEST python -m pytest -q tests/test_leaders_plain_secondary_receipt.py tests/test_leaders_topic_mode_routing.py tests/test_leaders_chat_bind_safety.py tests/test_leaders_native_workcenter.py tests/test_pulse_announcement_delivery.py
BOT_TOKEN=0000000000:LOCALTEST python -m pytest -q tests/test_event_announcement_recovery_fairness.py tests/test_event_quick_publication.py tests/test_event_wizard_publish_persistence.py
BOT_TOKEN=0000000000:LOCALTEST python -m pytest -q tests/test_event_card_transport.py tests/test_event_photo_contracts.py tests/test_event_registration_block14.py tests/test_media_notifications.py tests/test_full_bot_flow.py
BOT_TOKEN=0000000000:LOCALTEST python -m pytest -q tests/test_general_topics.py tests/test_event_quick_publication.py tests/test_native_event_composer.py
python -m ruff check app --select E9,F
```
PostgreSQL probes запускать только с PYTHONPATH=. и DATABASE_URL изолированного PostgreSQL era_test: scripts/postgres_leaders_workcenter_race.py и scripts/postgres_event_announcement_recovery_race.py. Production данные для тестов не использовать.

## Непроверенное, риски и границы

Полная многоролевая приёмка Mini App/Telegram, реальные топики/закрепы/доставка, приватность/портфолио и полное функциональное ТЗ не доказаны. Backup/restore27.10 подтверждён, новый24ч период стабильности после функционального LIVE ещё не завершён. Юридическое утверждение draft#364, организационные условия, согласия/провайдеры и вопросы доступа остаются открытыми. Сверять остаток с docs/MEDIA_DEPARTMENT_SPEC_2026_10_24.md и текущим кодом, не повторять уже выпущенные функции.

Разрешены код/ветки/PR/CI, совместимый безопасный merge после обязательных проверок и штатный выпуск. Без отдельного разрешения запрещены удаление реальных данных, изменение баллов/участия, массовые сообщения, публикация объявлений/событий, изменение реальных Telegram-чатов/ролей, секретов, опасные миграции, личные Telegram-сессии и ослабление безопасности. Эти ограничения28.10 приоритетнее старых разрешений рассылок. Высокий риск оставлять в PR.

Существующая hourly automation `6adcbd42ede08191a5c0a946e4147b52` обновлена на новый автономный цикл, исходный cadence сохранён, дубликат не создан. Обычные уведомления ТОЛЬКО09:00–19:00 Asia/Yerevan; ночью работать и сохранять результат, без обычного отчёта. Дневной монитор остаётся read-only. Лимиты не обходить; следующий доступный запуск читает checkpoint и продолжает.
