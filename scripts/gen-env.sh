#!/usr/bin/env bash
# Genere un .env local avec des secrets aleatoires (jamais commite).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { echo ".env existe deja, rien a faire"; exit 0; }
rnd() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
fernet() { head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }
cat > .env <<ENV
POSTGRES_PASSWORD=$(rnd 24)
REDIS_PASSWORD=$(rnd 24)
S3_ACCESS_KEY=$(rnd 16)
S3_SECRET_KEY=$(rnd 32)
JWT_SECRET=$(rnd 48)
FILE_ENCRYPTION_KEY=$(fernet)
ADMIN_PASSWORD=$(rnd 20)
ENV
chmod 600 .env
echo ".env genere (administrateur : admin@helpdesk.example.com / voir ADMIN_PASSWORD dans .env)"
