"""Tests unitaires des tâches du worker (base, SMTP et S3 remplacés par des doubles)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("FILE_ENCRYPTION_KEY", Fernet.generate_key().decode())

import tasks  # noqa: E402


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.rows, self.executed = rows, []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeResult(self.rows)

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_notify_created_sends_mail_to_author(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks, "_db", lambda: FakeConn([("Imprimante HS", "high", "alice@example.com", "Alice")]))
    monkeypatch.setattr(tasks, "_send_mail", lambda to, subject, body: sent.append((to, subject, body)))
    tasks.notify_ticket_created(7)
    assert sent[0][0] == "alice@example.com"
    assert "#7" in sent[0][1] and "Imprimante HS" in sent[0][2]


def test_notify_created_ignores_unknown_ticket(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks, "_db", lambda: FakeConn([]))
    monkeypatch.setattr(tasks, "_send_mail", lambda *a: sent.append(a))
    tasks.notify_ticket_created(999)
    assert sent == []


def test_export_is_encrypted_before_upload(monkeypatch):
    key = Fernet.generate_key().decode()
    # Settings est un dataclass fige : on contourne uniquement pour le test
    object.__setattr__(tasks.settings, "file_encryption_key", key)
    uploaded = {}

    class FakeS3:
        def put_object(self, **kw):
            uploaded.update(kw)

    rows = [(1, "Titre secret", "open", "normal", "a@x.fr", None, __import__("datetime").datetime(2026, 1, 1))]
    conn = FakeConn(rows)
    monkeypatch.setattr(tasks, "_db", lambda: conn)
    monkeypatch.setattr(tasks, "_s3", lambda: FakeS3())
    tasks.generate_export(3)
    assert b"Titre secret" not in uploaded["Body"]
    assert b"Titre secret" in Fernet(key.encode()).decrypt(uploaded["Body"])
    assert any("status='done'" in sql for sql, _ in conn.executed)


def test_failed_export_marks_job_failed(monkeypatch):
    class Boom(FakeConn):
        def execute(self, sql, params=None):
            if sql.lstrip().upper().startswith("SELECT"):
                raise RuntimeError("base indisponible")
            return super().execute(sql, params)

    conn = Boom([])
    monkeypatch.setattr(tasks, "_db", lambda: conn)
    with pytest.raises(RuntimeError):
        tasks.generate_export(4)
    assert any("status='failed'" in sql for sql, _ in conn.executed)
