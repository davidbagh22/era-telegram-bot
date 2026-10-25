# Render hotfix

Причина падения Render: Alembic видел несколько head revisions и команда `alembic upgrade head` завершалась ошибкой.

Изменение: Dockerfile теперь запускает `alembic upgrade heads`, чтобы применялись все текущие головы миграций.

Дальше нужно отдельно привести Alembic-цепочку к одной голове через merge migration, но этот фикс разблокирует deploy.
