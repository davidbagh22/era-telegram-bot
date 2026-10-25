#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_FILE:?BACKUP_FILE is required}"
: "${BACKUP_TYPE:?BACKUP_TYPE is required}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET is required}"

if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "Encrypted backup file is missing or empty" >&2
  exit 1
fi

case "${BACKUP_TYPE}" in
  daily) KEEP_COUNT=7 ;;
  weekly) KEEP_COUNT=4 ;;
  monthly) KEEP_COUNT=6 ;;
  manual) KEEP_COUNT=3 ;;
  *) echo "Unsupported BACKUP_TYPE=${BACKUP_TYPE}" >&2; exit 2 ;;
esac

PREFIX="${BACKUP_S3_PREFIX:-era-backups}"
PREFIX="${PREFIX#/}"
PREFIX="${PREFIX%/}"
OBJECT_KEY="${PREFIX}/${BACKUP_TYPE}/$(basename "${BACKUP_FILE}")"

AWS_ARGS=()
if [[ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]]; then
  AWS_ARGS+=(--endpoint-url "${BACKUP_S3_ENDPOINT_URL}")
fi
if [[ -n "${BACKUP_S3_REGION:-}" ]]; then
  export AWS_DEFAULT_REGION="${BACKUP_S3_REGION}"
fi

aws "${AWS_ARGS[@]}" s3 cp \
  "${BACKUP_FILE}" \
  "s3://${BACKUP_S3_BUCKET}/${OBJECT_KEY}" \
  --only-show-errors

# Exact count retention, independent from provider lifecycle settings.
# list-objects-v2 returns LastModified; jq sorts newest-first and emits
# only objects beyond the keep budget. Never touches another tier/prefix.
LIST_JSON="$(aws "${AWS_ARGS[@]}" s3api list-objects-v2 \
  --bucket "${BACKUP_S3_BUCKET}" \
  --prefix "${PREFIX}/${BACKUP_TYPE}/" \
  --output json)"

mapfile -t OLD_KEYS < <(
  printf '%s' "${LIST_JSON}" \
    | jq -r --argjson keep "${KEEP_COUNT}" \
      '(.Contents // []) | sort_by(.LastModified) | reverse | .[$keep:][]?.Key'
)

for key in "${OLD_KEYS[@]:-}"; do
  [[ -z "${key}" ]] && continue
  aws "${AWS_ARGS[@]}" s3api delete-object \
    --bucket "${BACKUP_S3_BUCKET}" \
    --key "${key}" >/dev/null
done

printf 's3://%s/%s\n' "${BACKUP_S3_BUCKET}" "${OBJECT_KEY}"
