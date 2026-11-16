#!/bin/sh
# Sauvegarde logique de la base, chiffree avant de quitter le pod, deposee dans le bucket "backups".
set -eu

: "${DB_HOST:?}" "${DB_USER:?}" "${DB_NAME:?}" "${DB_PASSWORD:?}" "${S3_ENDPOINT:?}"
: "${S3_ACCESS_KEY:?}" "${S3_SECRET_KEY:?}" "${BACKUP_PASSPHRASE:?}"
BUCKET="${S3_BUCKET_BACKUPS:-backups}"
REGION="${S3_REGION:-eu-west-3}"
KEEP="${BACKUP_KEEP:-7}"
EMPTY_SHA=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

s3() { # s3 <methode> <chemin> [options curl...]
  m="$1"; p="$2"; shift 2
  curl -sS --fail --aws-sigv4 "aws:amz:${REGION}:s3" --user "${S3_ACCESS_KEY}:${S3_SECRET_KEY}" -X "$m" "$@" "${S3_ENDPOINT}/${p}"
}

TS=$(date -u +%Y%m%dT%H%M%SZ)
FILE="/tmp/helpdesk-${TS}.sql.gz.enc"
export PGPASSWORD="$DB_PASSWORD"

echo "[backup] pg_dump de ${DB_NAME}@${DB_HOST}"
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" --no-owner --format=plain \
  | gzip -9 \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$FILE"

SIZE=$(wc -c < "$FILE")
HASH=$(sha256sum "$FILE" | cut -d' ' -f1)
KEY="db/$(basename "$FILE")"
s3 PUT "${BUCKET}/${KEY}" -H "x-amz-content-sha256: ${HASH}" -T "$FILE" -o /dev/null
echo "[backup] OK ${KEY} (${SIZE} octets, sha256 ${HASH})"
rm -f "$FILE"

# retention : on garde les KEEP sauvegardes les plus recentes
KEYS=$(s3 GET "${BUCKET}?list-type=2&prefix=db/" -H "x-amz-content-sha256: ${EMPTY_SHA}" \
  | grep -o '<Key>[^<]*</Key>' | sed 's/<[^>]*>//g' | sort)
COUNT=$(printf '%s\n' "$KEYS" | grep -c . || true)
if [ "$COUNT" -gt "$KEEP" ]; then
  printf '%s\n' "$KEYS" | head -n "$((COUNT - KEEP))" | while read -r old; do
    s3 DELETE "${BUCKET}/${old}" -H "x-amz-content-sha256: ${EMPTY_SHA}" -o /dev/null
    echo "[backup] ancienne sauvegarde supprimee : ${old}"
  done
fi
echo "[backup] termine, ${KEEP} sauvegardes conservees au maximum"
