#!/bin/sh
# Restaure la derniere sauvegarde (ou BACKUP_KEY) dans la base TARGET_DB (par defaut helpdesk_restore).
set -eu

: "${DB_HOST:?}" "${DB_USER:?}" "${DB_PASSWORD:?}" "${S3_ENDPOINT:?}" "${S3_ACCESS_KEY:?}" "${S3_SECRET_KEY:?}" "${BACKUP_PASSPHRASE:?}"
BUCKET="${S3_BUCKET_BACKUPS:-backups}"
REGION="${S3_REGION:-eu-west-3}"
TARGET_DB="${TARGET_DB:-helpdesk_restore}"
EMPTY_SHA=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
export PGPASSWORD="$DB_PASSWORD"

s3() { m="$1"; p="$2"; shift 2
  curl -sS --fail --aws-sigv4 "aws:amz:${REGION}:s3" --user "${S3_ACCESS_KEY}:${S3_SECRET_KEY}" -X "$m" "$@" "${S3_ENDPOINT}/${p}"; }

KEY="${BACKUP_KEY:-}"
if [ -z "$KEY" ]; then
  KEY=$(s3 GET "${BUCKET}?list-type=2&prefix=db/" -H "x-amz-content-sha256: ${EMPTY_SHA}" \
    | grep -o '<Key>[^<]*</Key>' | sed 's/<[^>]*>//g' | sort | tail -n 1)
fi
echo "[restore] sauvegarde utilisee : ${KEY}"
s3 GET "${BUCKET}/${KEY}" -H "x-amz-content-sha256: ${EMPTY_SHA}" -o /tmp/restore.enc

psql -h "$DB_HOST" -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${TARGET_DB}" -c "CREATE DATABASE ${TARGET_DB}"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in /tmp/restore.enc | gunzip \
  | psql -h "$DB_HOST" -U "$DB_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 -q
echo "[restore] base ${TARGET_DB} restauree, lignes par table :"
psql -h "$DB_HOST" -U "$DB_USER" -d "$TARGET_DB" -At -c \
  "SELECT 'users=' || count(*) FROM users UNION ALL SELECT 'tickets=' || count(*) FROM tickets UNION ALL SELECT 'attachments=' || count(*) FROM attachments"
