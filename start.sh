#!/bin/sh
set -eu

alembic upgrade heads

if [ -n "${LAST_KEEPER_BOT_TOKEN:-}" ]; then
  echo "Starting Last Keeper Telegram bot"
  (
    export BOT_TOKEN="$LAST_KEEPER_BOT_TOKEN"
    export ADMIN_IDS="${LAST_KEEPER_ADMIN_IDS:-${ADMIN_IDS:-}}"
    export DATABASE_PATH="${LAST_KEEPER_DATABASE_PATH:-/tmp/last_keeper.db}"
    exec python last_keeper_bot/run.py
  ) &
else
  echo "LAST_KEEPER_BOT_TOKEN is not configured; Last Keeper bot is disabled"
fi

exec uvicorn app.webapp:app --host 0.0.0.0 --port "${PORT:-8000}"
