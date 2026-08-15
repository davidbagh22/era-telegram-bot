#!/usr/bin/env bash
set -Eeuo pipefail

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
: "${PG_MAJOR:?PG_MAJOR is required}"

PG_BIN="${PG_BIN:-/usr/lib/postgresql/${PG_MAJOR}/bin}"
PG_RESTORE="${PG_BIN}/pg_restore"
PSQL="${PG_BIN}/psql"

for binary in "${PG_RESTORE}" "${PSQL}"; do
  if [[ ! -x "${binary}" ]]; then
    echo "Required PostgreSQL ${PG_MAJOR} restore client is unavailable" >&2
    exit 1
  fi
done

if ! "${PG_RESTORE}" --version | grep -Eq "PostgreSQL\) ${PG_MAJOR}\."; then
  echo "pg_restore major does not match required PostgreSQL major" >&2
  exit 1
fi
if ! "${PSQL}" --version | grep -Eq "PostgreSQL\) ${PG_MAJOR}\."; then
  echo "psql major does not match required PostgreSQL major" >&2
  exit 1
fi

if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "Backup file does not exist or is empty" >&2
  exit 1
fi

if [[ -n "${BACKUP_SHA256:-}" ]]; then
  ACTUAL_SHA256="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
  if [[ "${ACTUAL_SHA256}" != "${BACKUP_SHA256}" ]]; then
    echo "Backup checksum mismatch" >&2
    exit 1
  fi
fi

"${PG_RESTORE}" \
  --dbname="${RESTORE_DATABASE_URL}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  "${BACKUP_FILE}"

"${PSQL}" "${RESTORE_DATABASE_URL}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'users'
  ) THEN
    RAISE EXCEPTION 'Required table public.users is missing after restore';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'alembic_version'
  ) THEN
    RAISE EXCEPTION 'Required table public.alembic_version is missing after restore';
  END IF;
END $$;
SQL

CODE_HEADS="$(alembic heads | awk '{print $1}' | sort -u)"
RESTORED_HEADS="$("${PSQL}" "${RESTORE_DATABASE_URL}" -At -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version ORDER BY version_num;' | sort -u)"

if [[ -z "${CODE_HEADS}" || -z "${RESTORED_HEADS}" || "${CODE_HEADS}" != "${RESTORED_HEADS}" ]]; then
  echo "Restored Alembic revision does not match code migration head(s)" >&2
  exit 1
fi

"${PSQL}" "${RESTORE_DATABASE_URL}" -At -v ON_ERROR_STOP=1 -c \
  "SELECT CASE WHEN EXISTS (SELECT 1 FROM public.users LIMIT 1) THEN 'users_table_readable' ELSE 'users_table_readable_empty' END;" \
  >/dev/null

echo "Restore verification completed successfully"
