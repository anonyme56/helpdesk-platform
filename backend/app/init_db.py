"""Initialisation idempotente : tables et administrateur initial.

Lancé au démarrage (initContainer / service compose). Un verrou advisory Postgres évite
que plusieurs réplicas créent les tables en même temps.
"""
import logging
import time

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, get_engine
from .logging_conf import setup_logging
from .models import User
from .security import hash_password
from .services import get_storage

log = logging.getLogger("init")


def wait_for_db(engine, retries: int = 30):
    for _ in range(retries):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception as e:  # noqa: BLE001
            log.info("base pas prête (%s), nouvel essai", type(e).__name__)
            time.sleep(2)
    raise SystemExit("base de données injoignable")


def ensure_buckets(retries: int = 30):
    s, client = get_settings(), get_storage().client
    for bucket in (s.s3_bucket_attachments, s.s3_bucket_exports, s.s3_bucket_backups):
        for _ in range(retries):
            try:
                existing = {b["Name"] for b in client.list_buckets()["Buckets"]}
                if bucket not in existing:
                    client.create_bucket(Bucket=bucket)
                    log.info("bucket créé : %s", bucket)
                break
            except Exception as e:  # noqa: BLE001
                log.info("stockage objet pas prêt (%s), nouvel essai", type(e).__name__)
                time.sleep(2)
        else:
            raise SystemExit("stockage objet injoignable")


def main():
    s = get_settings()
    setup_logging(s.log_level)
    engine = get_engine()
    wait_for_db(engine)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
        Base.metadata.create_all(conn)
    with Session(engine) as db:
        if s.admin_password and not db.scalar(select(User).where(User.email == s.admin_email)):
            db.add(User(email=s.admin_email, full_name="Administrateur", role="admin",
                        password_hash=hash_password(s.admin_password)))
            db.commit()
            log.info("administrateur initial créé")
    ensure_buckets()
    log.info("initialisation terminée")


if __name__ == "__main__":
    main()
