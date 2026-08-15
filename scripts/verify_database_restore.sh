#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_FILE:?BACKUP_FILE is required}"

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

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required for isolated restore verification" >&2
  exit 1
}

CONTAINER="era-restore-${GITHUB_RUN_ID:-$$}-${RANDOM}"
cleanup() {
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d \
  --name "${CONTAINER}" \
  -e POSTGRES_USER=restore \
  -e POSTGRES_PASSWORD=restore \
  -e POSTGRES_DB=era_restore_check \
  postgres:18 >/dev/null

for _ in $(seq 1 30); do
  if docker exec "${CONTAINER}" pg_isready -U restore -d era_restore_check >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec "${CONTAINER}" pg_isready -U restore -d era_restore_check >/dev/null

docker cp "${BACKUP_FILE}" "${CONTAINER}:/tmp/era-production.dump" >/dev/null

docker exec \
  -e PGPASSWORD=restore \
  "${CONTAINER}" \
  pg_restore \
    --username=restore \
    --dbname=era_restore_check \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    /tmp/era-production.dump

docker exec \
  -e PGPASSWORD=restore \
  "${CONTAINER}" \
  psql \
    --username=restore \
    --dbname=era_restore_check \
    --no-psqlrc \
    -v ON_ERROR_STOP=1 \
    -c "SELECT to_regclass('public.users') IS NOT NULL AS users_table_present" \
  | grep -q 't'

echo "Restore verification completed successfully"
