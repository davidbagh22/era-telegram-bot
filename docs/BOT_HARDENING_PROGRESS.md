# BOT HARDENING PROGRESS

## Текущий статус

Оценка готовности: 6/10.

Этап 1: база данных и транзакции — локально выполнен, PR #66 открыт.

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

Merge commit: pending.

CI:
- Tests: pending;
- Bot checks: pending.

## Открытые проблемы

- Production backup нельзя считать подтверждённым без `BACKUP_DATABASE_URL` и реального artifact restore.
- Production Render / Telegram smoke test не проверялись.

## Следующий этап

Этап 2. Система баллов:
- покрыть idempotency key все источники начисления и списания;
- проверить старые callback/update/быстрые нажатия;
- унифицировать `source_type`, `source_id` и причины операций.
