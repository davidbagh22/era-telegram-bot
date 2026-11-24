#!/usr/bin/env bash
# Verify the bytes actually stored by the provider, then restore on the CI clone.
set -Eeuo pipefail
: "${EXTERNAL_REFERENCE:?EXTERNAL_REFERENCE is required}"
: "${ARCHIVE_SHA256:?ARCHIVE_SHA256 is required}"
: "${BACKUP_SHA256:?BACKUP_SHA256 is required}"
: "${BACKUP_ENCRYPTION_KEY:?BACKUP_ENCRYPTION_KEY is required}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
# Never allow an external-copy drill to target production.
"${RESTORE_PYTHON:-python3}" - <<'PY'
import os
from urllib.parse import urlsplit
url = urlsplit(os.environ['RESTORE_DATABASE_URL'])
if url.hostname not in {'localhost', '127.0.0.1', '::1'} or url.path != '/era_restore_check':
    raise SystemExit('External backup verification requires the isolated CI database')
PY
umask 077
VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "${VERIFY_DIR}"' EXIT
sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo 'sha256sum is required to validate the external backup' >&2
    exit 127
  fi
}
AWS_CMD=(aws)
if [[ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]]; then
  AWS_CMD+=(--endpoint-url "${BACKUP_S3_ENDPOINT_URL}")
fi
if [[ -n "${BACKUP_S3_REGION:-}" ]]; then
  export AWS_DEFAULT_REGION="${BACKUP_S3_REGION}"
fi
"${AWS_CMD[@]}" s3 cp "${EXTERNAL_REFERENCE}" "${VERIFY_DIR}/backup.enc" --only-show-errors
ACTUAL_SHA="$(sha256_file "${VERIFY_DIR}/backup.enc")"
if [[ "${ACTUAL_SHA}" != "${ARCHIVE_SHA256}" ]]; then
  echo 'External encrypted backup checksum mismatch' >&2
  exit 1
fi
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in "${VERIFY_DIR}/backup.enc" -out "${VERIFY_DIR}/backup.dump" \
  -pass env:BACKUP_ENCRYPTION_KEY
export BACKUP_FILE="${VERIFY_DIR}/backup.dump"
bash scripts/verify_database_restore.sh
