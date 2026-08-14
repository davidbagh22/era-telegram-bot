#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_KEY:?BACKUP_KEY is required}"

BACKUP_TYPE="${BACKUP_TYPE:-daily}"
BACKUP_STATUS="${BACKUP_STATUS:-success}"
STORAGE_PROVIDER="${STORAGE_PROVIDER:-backup-workflow}"
STORAGE_REFERENCE="${STORAGE_REFERENCE:-}"
CHECKSUM_SHA256="${CHECKSUM_SHA256:-}"
SIZE_BYTES="${SIZE_BYTES:-}"
STARTED_AT="${STARTED_AT:-}"
COMPLETED_AT="${COMPLETED_AT:-}"
RESTORE_VERIFIED_AT="${RESTORE_VERIFIED_AT:-}"
ERROR_CODE="${ERROR_CODE:-}"
ERROR_DETAIL="${ERROR_DETAIL:-}"

case "${BACKUP_STATUS}" in
  success|failed) ;;
  *)
    echo "Unsupported BACKUP_STATUS" >&2
    exit 2
    ;;
esac

# Production metadata is written through the same restricted backup database
# credential already required by pg_dump. psql variables keep values out of SQL
# string interpolation and the script never prints DATABASE_URL or secret data.
psql "${DATABASE_URL}" \
  --no-psqlrc \
  --set=ON_ERROR_STOP=1 \
  --set=backup_key="${BACKUP_KEY}" \
  --set=backup_type="${BACKUP_TYPE}" \
  --set=backup_status="${BACKUP_STATUS}" \
  --set=storage_provider="${STORAGE_PROVIDER}" \
  --set=storage_reference="${STORAGE_REFERENCE}" \
  --set=checksum_sha256="${CHECKSUM_SHA256}" \
  --set=size_bytes="${SIZE_BYTES}" \
  --set=started_at="${STARTED_AT}" \
  --set=completed_at="${COMPLETED_AT}" \
  --set=restore_verified_at="${RESTORE_VERIFIED_AT}" \
  --set=error_code="${ERROR_CODE}" \
  --set=error_detail="${ERROR_DETAIL}" <<'SQL'
INSERT INTO backup_history (
  backup_key,
  backup_type,
  status,
  storage_provider,
  storage_reference,
  checksum_sha256,
  size_bytes,
  started_at,
  completed_at,
  restore_verified_at,
  error_code,
  error_detail
)
VALUES (
  :'backup_key',
  :'backup_type',
  :'backup_status',
  :'storage_provider',
  NULLIF(:'storage_reference', ''),
  NULLIF(:'checksum_sha256', ''),
  NULLIF(:'size_bytes', '')::bigint,
  COALESCE(NULLIF(:'started_at', '')::timestamptz, now()),
  NULLIF(:'completed_at', '')::timestamptz,
  NULLIF(:'restore_verified_at', '')::timestamptz,
  NULLIF(:'error_code', ''),
  NULLIF(:'error_detail', '')
)
ON CONFLICT (backup_key) DO UPDATE SET
  backup_type = EXCLUDED.backup_type,
  status = EXCLUDED.status,
  storage_provider = EXCLUDED.storage_provider,
  storage_reference = EXCLUDED.storage_reference,
  checksum_sha256 = EXCLUDED.checksum_sha256,
  size_bytes = EXCLUDED.size_bytes,
  started_at = EXCLUDED.started_at,
  completed_at = EXCLUDED.completed_at,
  restore_verified_at = EXCLUDED.restore_verified_at,
  error_code = EXCLUDED.error_code,
  error_detail = EXCLUDED.error_detail;
SQL

printf '%s\n' "Backup History metadata recorded for ${BACKUP_KEY}"