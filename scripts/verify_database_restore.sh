#!/usr/bin/env bash
set -Eeuo pipefail

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"

if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "Backup file does not exist or is empty: ${BACKUP_FILE}" >&2
  exit 1
fi

if [[ -n "${BACKUP_SHA256:-}" ]]; then
  ACTUAL_SHA256="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
  if [[ "${ACTUAL_SHA256}" != "${BACKUP_SHA256}" ]]; then
    echo "Backup checksum mismatch" >&2
    exit 1
  fi
fi

pg_restore \
  --dbname="${RESTORE_DATABASE_URL}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  "${BACKUP_FILE}"

psql "${RESTORE_DATABASE_URL}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'users'
  ) THEN
    RAISE EXCEPTION 'Required table public.users is missing after restore';
  END IF;
END $$;

SELECT COUNT(*) AS users_count FROM users;
SQL

echo "Restore verification completed successfully"
