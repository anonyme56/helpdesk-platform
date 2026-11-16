# Sauvegardes PostgreSQL -> stockage objet : pg_dump, compression, chiffrement AES-256, envoi signe (SigV4)
FROM postgres:16-alpine
# versions apk non figees : les index Alpine retirent les anciens paquets, la reproductibilite vient du tag de base
# hadolint ignore=DL3018
RUN apk add --no-cache curl openssl
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh
USER 70
CMD ["/usr/local/bin/backup.sh"]
