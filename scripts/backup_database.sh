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

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo 'sha256sum is required to verify the backup payload' >&2
    exit 127
  fi
}

sha_file_size() {
  if stat -c '%s' "$1" >/dev/null 2>&1; then
    stat -c '%s' "$1"
  else
    stat -f '%z' "$1"
  fi
}

SHA256="$(sha256_file "${DUMP_PATH}")"
SIZE_BYTES="$(sha_file_size "${DUMP_PATH}")"
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
