# ЭРА: отчёт по изменениям 17.10.2026

Аудит исходного состояния сохранён в AUDIT.md и AUDIT_CODE_INVENTORY.md. Полная матрица — FUNCTIONAL_MATRIX.md; остаток — MASTER_REMAINDER.md; инструкция — NATIVE_ADMIN_GUIDE.md.

## Реализовано

- #342: прямые кнопки «Админ-сводка», «Заявки», «Открыть ЭРА»; HTML-сводки и Excel; native рассмотрение с версиями карточек и commit-before-notice. Одобрение синхронизирует ожидающий join request, сохраняя санкции модератора. Быстрая регистрация, продолжение анкеты, повторная подача без нового User/потери интересов. Игровые темы/вопросы выбираются разнообразно с общей историей quiz и проверкой 180 дней.
- #343: резервная копия защищает фактически работающую здоровую БД, не ждёт старый workflow SHA при rerun. OIDC и isolated restore сохранены; artifact включает run_attempt.
- #344: native обращения и ответ, durable/deduplicated intake, редакционная очередь литературы, private SLA, pause/resume/cancel существующих campaigns, общий адаптивный transport. Миграций нет; chat/thread IDs неизменны.
- Исправлен обнаруженный startup failure Render: пустая строка списка получателей отчёта заменена JSON-массивом []. Добавлен тест реального env loader. Задержанный menu readback проверяется ограниченно и даёт безопасный reason; feature flags наблюдаемы без токенов и персональных ID.
- Подготовлены три литературных черновика с источниками. Они не загружены в production и не утверждены автоматически.

## Проверки и границы доказательства

Initial local native suite: 1720 passed, 1 skipped, 1 xfailed, 58 subtests. Дальнейший exec-server отключился; прерванный local run второго пакета не засчитывается.

PostgreSQL proof до финального fixture-only исправления: восемь одновременных решений заявки дают одно решение/награду; восемь workers дают один литературный выпуск, один intake и один ответ; rollback intake не уведомляет; concurrent cancel выигрывает у завершения отправки. Browser: 39 passed, 2 skipped; Redis FSM checks: 2 passed. Два legacy FAQ mocks обновлены к новому service contract. Обязательное окончательное доказательство — полный CI точного head в PR #344; не считать частичный прогон его заменой.

## Production-протокол

Подтверждённый исходный live этого этапа: 36de387006b9fa9c1f5b1e0836c1c21601372329, Render dep-db9f953m8hqs73aevf8g. /health и /ready дали HTTP 200 в Render logs. Backup 17.10.2026 04:08:35 UTC, 1 555 232 байта, success + isolated restore; healthy source 36de387. Alembic: 0061_notification_message.

Финальный runtime SHA самопроверяющего коммита не записывается предположением: **итоговый SHA, deploy ID, health, проверенные flags и результат финального CI добавляются после Render live в описание [PR #344](https://github.com/davidbagh22/era-telegram-bot/pull/344)**. Этот раздел не объявляет ещё не подтверждённый выпуск успешным.

## Остаток

Функциональные пробелы и необходимые реальные действия отделены в MASTER_REMAINDER.md. Новые категории/owner/многоходовая переписка, полная delegated matrix и phase 8 не выдаются за завершённые. Политика для несовершеннолетних, редакторское утверждение, independent S3 и настоящая Telegram-приёмка не заменяются автоматическими тестами.
