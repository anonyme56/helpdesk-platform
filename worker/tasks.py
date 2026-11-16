"""Tâches de fond exécutées par le worker RQ.

Le backend les enfile par nom ("tasks.notify_ticket_created", ...), le worker les importe ici.
Chaque tâche est comptée dans Prometheus (succès / échec / durée).
"""
import csv
import io
import logging
import smtplib
import time
from datetime import UTC, datetime
from email.message import EmailMessage
from functools import wraps

import boto3
import psycopg
from botocore.client import Config
from prometheus_client import Counter, Histogram

from config import settings
from crypto import ObjectCipher

log = logging.getLogger("tasks")

JOBS = Counter("worker_jobs_total", "Tâches traitées par le worker", ["task", "result"])
JOB_DURATION = Histogram("worker_job_duration_seconds", "Durée des tâches", ["task"],
                         buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))


def tracked(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            out = fn(*args, **kwargs)
        except Exception:
            JOBS.labels(fn.__name__, "failed").inc()
            log.exception("tâche en échec", extra={"fields": {"task": fn.__name__, "args": args}})
            raise
        JOBS.labels(fn.__name__, "ok").inc()
        JOB_DURATION.labels(fn.__name__).observe(time.perf_counter() - started)
        log.info("tâche terminée", extra={"fields": {"task": fn.__name__, "args": args}})
        return out

    return wrapper


def _db():
    return psycopg.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
        user=settings.db_user, password=settings.db_password, connect_timeout=5,
    )


def _s3():
    return boto3.client(
        "s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _send_mail(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    # local_hostname fixe : sans lui smtplib fait un getfqdn() (DNS inverse) qui coute ~4 s par mail en conteneur
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10, local_hostname="helpdesk-worker") as smtp:
        smtp.send_message(msg)


@tracked
def notify_ticket_created(ticket_id: int) -> None:
    with _db() as conn:
        row = conn.execute(
            "SELECT t.title, t.priority, u.email, u.full_name FROM tickets t "
            "JOIN users u ON u.id = t.author_id WHERE t.id = %s", (ticket_id,)
        ).fetchone()
    if row is None:
        log.warning("ticket introuvable", extra={"fields": {"ticket_id": ticket_id}})
        return
    title, priority, email, name = row
    _send_mail(email, f"[Helpdesk] Ticket #{ticket_id} enregistré",
               f"Bonjour {name},\n\nVotre demande « {title} » (priorité {priority}) a bien été "
               f"enregistrée sous le numéro {ticket_id}.\nNous revenons vers vous rapidement.\n")


@tracked
def notify_ticket_assigned(ticket_id: int) -> None:
    with _db() as conn:
        row = conn.execute(
            "SELECT t.title, t.priority, a.email, a.full_name FROM tickets t "
            "JOIN users a ON a.id = t.assignee_id WHERE t.id = %s", (ticket_id,)
        ).fetchone()
    if row is None:
        return
    title, priority, email, name = row
    _send_mail(email, f"[Helpdesk] Ticket #{ticket_id} vous est assigné",
               f"Bonjour {name},\n\nLe ticket #{ticket_id} « {title} » (priorité {priority}) vous a été assigné.\n")


@tracked
def generate_export(job_id: int) -> None:
    """Exporte tous les tickets en CSV dans le bucket 'exports'."""
    with _db() as conn:
        conn.execute("UPDATE export_jobs SET status='running' WHERE id=%s", (job_id,))
        conn.commit()
        try:
            rows = conn.execute(
                "SELECT t.id, t.title, t.status, t.priority, a.email, s.email, t.created_at "
                "FROM tickets t JOIN users a ON a.id = t.author_id "
                "LEFT JOIN users s ON s.id = t.assignee_id ORDER BY t.id"
            ).fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["id", "titre", "statut", "priorite", "auteur", "assigne", "cree_le"])
            for r in rows:
                w.writerow([c.isoformat() if isinstance(c, datetime) else c for c in r])
            key = f"exports/{datetime.now(UTC):%Y%m%d}/tickets_{job_id}.csv"
            payload = ObjectCipher(settings.file_encryption_key).encrypt(buf.getvalue().encode("utf-8"))
            _s3().put_object(Bucket=settings.s3_bucket_exports, Key=key, Body=payload,
                             ContentType="text/csv")
            conn.execute("UPDATE export_jobs SET status='done', object_key=%s, finished_at=now() WHERE id=%s",
                         (key, job_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.execute("UPDATE export_jobs SET status='failed', error=%s, finished_at=now() WHERE id=%s",
                         (str(e)[:500], job_id))
            conn.commit()
            raise
