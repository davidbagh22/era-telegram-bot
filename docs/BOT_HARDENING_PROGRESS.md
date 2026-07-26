# BOT HARDENING PROGRESS

## Текущий статус

Оценка готовности: 7/10.

Этап 1: база данных и транзакции — завершён и смержен в `main`.

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

PR: pending.

Merge commit: pending.

CI:
- Tests: pending;
- Bot checks: pending.

## Открытые проблемы

- Production backup нельзя считать подтверждённым без `BACKUP_DATABASE_URL` и реального artifact restore.
- Production Render / Telegram smoke test не проверялись.

## Следующий этап

Этап 3. Роли и права:
- построить фактическую матрицу ролей;
- проверить административные handlers на обход прав;
- добавить негативные тесты на чужие ID, callback-подмену и ручные команды.
