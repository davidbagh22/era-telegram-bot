#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"

BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASENAME="era-postgres-${TIMESTAMP}"
DUMP_PATH="${BACKUP_DIR}/${BASENAME}.dump"
MANIFEST_PATH="${BACKUP_DIR}/${BASENAME}.json"

mkdir -p "${BACKUP_DIR}"

pg_dump \
  --dbname="${DATABASE_URL}" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-privileges \
  --file="${DUMP_PATH}"

if [[ ! -s "${DUMP_PATH}" ]]; then
  echo "Backup file is empty" >&2
  exit 1
fi

SHA256="$(sha256sum "${DUMP_PATH}" | awk '{print $1}')"
SIZE_BYTES="$(stat -c '%s' "${DUMP_PATH}")"
PG_VERSION="$(pg_dump --version | sed 's/"/\\"/g')"

cat > "${MANIFEST_PATH}" <<EOF
{
  "created_at_utc": "${TIMESTAMP}",
  "file": "$(basename "${DUMP_PATH}")",
  "sha256": "${SHA256}",
  "size_bytes": ${SIZE_BYTES},
  "pg_dump_version": "${PG_VERSION}",
  "retention_days": ${RETENTION_DAYS}
}
EOF

find "${BACKUP_DIR}" -type f \( -name 'era-postgres-*.dump' -o -name 'era-postgres-*.json' \) -mtime "+${RETENTION_DAYS}" -delete

printf '%s\n' "${DUMP_PATH}"
