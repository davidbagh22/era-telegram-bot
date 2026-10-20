# Состояние ЭРА — 20.10.2026

## Production / сброс — выполнено
- PR #356 MERGED, main/prod bcb029947459380a8e690cf06711f7f817b5f974. Render LIVE dep-dbbb03bm8hqs738ocb80, 20.10 00:05 UTC. /health и /ready = 200, health commit bcb0299.
- Точный целевой Telegram ID предоставлен пользователем. Reset receipt = complete, encrypted_snapshot присутствует. Старый user_id=31 архивирован с синтетическим Telegram ID, community identity user_id=NULL. Активной users-записи с исходным ID пока нет: доступна новая регистрация через /start. Прежний ledger сохранён: 2 записи / 105 баллов. Связей leader_chat_memberships нет. Ключ резервной копии остаётся только в Render env, не публиковать и не регенерировать.
- Полная реальная повторная отправка анкеты самим пользователем ещё не наблюдалась; не объявлять её проверенной через Telegram-клиент.

## Аналитика и фотографии — PR #357, финальный выпуск
- Последний полный CI remote ca2418ff67f1639a80e3b115d5abb25977c13838: оба workflows success, все 6 jobs success. Main остаётся bcb0299. Перед merge повторить проверки нового head.
- Общий verified SQL snapshot 7/30/90, first audit approval, retention в одном SQL statement, наблюдаемая воронка 90 дней без восстановления истории из текущей роли. Native Telegram/API/Excel, health/efficiency/dashboard используют общие факты. Лимиты 500/200 удалены; проверены 501/501/201.
- Scoped результаты лидеров: свежие tasks.manage grants/offices, своя область, нагрузка/результаты/цели. Обычная роль leader не выдаёт глобальные права. Events: явка отдельно от регистрации и баллов, реальные отзывы. Projects: статусы отдельно от подтверждённых вкладов/этапов. Delivery warnings по существующим receipts, чтение ничего не отправляет.
- Замечания review: открытые task-scoped блокеры включены в distinct attention, закрытые задачи исключены; approved/in_progress унифицированы как active projects в snapshot/dashboard/health/efficiency, статусы отдельно в project report. Добавлен регрессионный тест на одинаковые итоги и несколько блокеров одной задачи.
- Новый запрос пользователя: фото при регистрации. Исправлены две причины: текущий поток обнулял photo_file_id и не имел загрузки; автоматическая карточка игнорировала фото. В quick/full review есть необязательная кнопка загрузки/замены, предпросмотр и resume; фото сохраняется после submit/resubmit, администраторы получают photo+caption <1024 через прежний durable receipt. Недоступное фото не скрывает текст анкеты. Старые consent/FSM остаются совместимыми.
- Адресные проверки до финального push: 58 passed + 12 subtests, дополнительные 25 passed; lint passed. Изменения photo resubmit и аналитики требуют CI нового head. Изолированный PostgreSQL probe выполняет все builders 7/30/90.

## Следующие действия
1. Remote #357 = 6faa39932143aa6ed5cc634c07a07cea23a87663, его CI запущен. Последующий точечный fix учитывает UTF-16/emoji в caption; перед продолжением сверить фактический remote head и tree. Два review threads исправлены и resolved. Других открытых PR нет.
2. Full CI нового head, resolve двух исправленных threads, merge #357 → штатный auto deploy после main checksPass (не запускать лишний deploy).
3. Проверить prod SHA, /ready, startup/logs и router/export wiring. Реальную загрузку фото и отправку анкеты из Telegram-клиента не объявлять проверенной без факта.
4. Security: ipAllowList 0.0.0.0/0 НЕ изменён. Нет update ACL в Render MCP; browser login request истёк, прежняя вкладка отсутствует. Не считать timeout отказом/успехом и не извлекать credentials. Для UI изменения нужен действующий вход Render.
5. Backup: scheduled run 39377805234 success 20.10 06:00 UTC. Workflow использует OIDC HTTPS snapshot через внутренний PG, проверку restore и encrypted GitHub artifact. Bot/connector PG connections private; public=0. S3 extra layer требует отсутствующих credentials, GitHub уже независимый от Render слой.

## Остаток итогового ТЗ
Полная AM/EN локализация/редакторская приёмка; категорийное делегирование поддержки/редакции; независимый backup provider/ACL по факту доступов; реальные Telegram-клиентские сценарии и 24 часа наблюдения. Полный контракт: docs/ERA_FINAL_TZ_2026_10_19.md. Не выдавать CI за реальную приёмку.

Тесты запускать с BOT_TOKEN=0000000000:LOCALTEST в ../era-test-env. Комиссионный бот, его схему и чужие изменения не трогать. Начинать с этого файла и AI_WORK_MAP; не перечитывать весь проект.
