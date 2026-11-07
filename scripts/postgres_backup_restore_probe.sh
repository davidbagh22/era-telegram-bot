#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_PROBE_SOURCE_URL:?BACKUP_PROBE_SOURCE_URL is required}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"

python3 - <<'PY'
import os
from urllib.parse import urlsplit

expected = {
    "BACKUP_PROBE_SOURCE_URL": "/era_test",
    "RESTORE_DATABASE_URL": "/era_restore_check",
}
for name, path in expected.items():
    url = urlsplit(os.environ[name])
    if url.scheme not in {"postgres", "postgresql"} or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.path != path:
        raise SystemExit("Backup restore probe requires its isolated local PostgreSQL databases")
PY

PG_BIN="${PG_BIN:-$(dirname "$(command -v pg_restore)")}"
PG_DUMP="${PG_BIN}/pg_dump"
CREATEDB="${PG_BIN}/createdb"
if [[ ! -x "${PG_DUMP}" || ! -x "${CREATEDB}" ]]; then
  echo "Required PostgreSQL backup clients are unavailable" >&2
  exit 1
fi

"${CREATEDB}" --maintenance-db="${BACKUP_PROBE_SOURCE_URL}" era_restore_check
BACKUP_FILE="$(mktemp)"
trap 'rm -f "${BACKUP_FILE}"' EXIT
"${PG_DUMP}" --format=custom --file="${BACKUP_FILE}" "${BACKUP_PROBE_SOURCE_URL}"
BACKUP_SHA256="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
export BACKUP_FILE BACKUP_SHA256 PG_BIN
export ALEMBIC_BIN="${ALEMBIC_BIN:-alembic}"
export RESTORE_APPLY_MIGRATIONS=false
bash scripts/verify_database_restore.sh
