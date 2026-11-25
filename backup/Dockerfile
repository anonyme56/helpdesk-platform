# syntax=docker/dockerfile:1
# Sauvegardes PostgreSQL -> stockage objet : pg_dump, compression, chiffrement AES-256, envoi signe (SigV4).
# Alpine + client PostgreSQL seulement (et non l'image serveur postgres : 428 Mo -> voir rapport, partie FinOps).
FROM alpine:3.22
# versions apk non figees : les index Alpine retirent les anciens paquets, la reproductibilite vient du tag de base
# hadolint ignore=DL3018
RUN apk add --no-cache postgresql16-client curl openssl gzip \
 && apk upgrade --no-cache
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh
USER 70
CMD ["/usr/local/bin/backup.sh"]
