# Состояние ЭРА — 20.10.2026, после выпуска #357

## Последний проверенный production
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
1. PostgreSQL external allowlist всё ещё 0.0.0.0/0. Render MCP не предоставляет update ACL. Browser login не завершён, прежняя вкладка отсутствует; API-ключа/CLI в среде нет. Нужен действующий безопасный вход Render, затем internal-only и проверка bot/migrations/backup. Не заявлять, что сеть уже закрыта.
2. Дополнительная S3-копия без credentials провайдера не подключена. Независимый от Render encrypted GitHub backup УЖЕ работает: run 39377805234 success 20.10 06:00 UTC; download OIDC snapshot, isolated PG18 restore, encrypt/verify/upload artifact — success. S3 upload/download/restore skipped. Не путать отсутствие S3 с отсутствием резервной копии.
3. Полная AM/EN локализация основных маршрутов и содержательная редакторская приёмка; категорийное делегирование поддержки/редакции. Существующие global grants и scoped projects/tasks сохранены, admin root не расширять.
4. Реальная клиентская Telegram-приёмка: повторная анкета с фото самим пользователем, цикл задач с разными участниками, canary рассылки/игр/мероприятий. Не создавать фиктивных участников и массовые production-рассылки как тест. HTTP/CI не заменяют эти факты. 24 часа после выпуска ещё не прошли.

## Как продолжать экономно
Этот post-release checkpoint сохранён в ветке feat/analytics2-20261020, поверх main 13cdabde. В main документы могут описывать предвыпускной этап; сначала сверить фактические main/prod SHA и этот checkpoint, не повторять уже завершённый аудит/сброс/релиз. Карта: AI_WORK_MAP.md; формулы: AI_ANALYTICS_SPEC.md; полный остаток: ERA_FINAL_TZ_2026_10_19.md.

Тесты: BOT_TOKEN=0000000000:LOCALTEST ../era-test-env/bin/python -m pytest -q <точные тесты>. Изменения через отдельную ветку и PR. Не трогать commission-бот, его схему и чужой untracked файл app/.commission_bot_community.py.vo6FgJ. Не печатать secrets/анкеты/дампы. Не запускать ручной deploy при активном auto deploy.
